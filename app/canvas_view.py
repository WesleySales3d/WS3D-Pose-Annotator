"""Annotation canvas based on QGraphicsView."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsLineItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from .annotation_model import FrameAnnotation
from .keypoint_item import KeypointItem
from .keypoint_table import KEYPOINT_MIME_TYPE
from .settings import DEFAULT_LINE_WIDTH, DEFAULT_POINT_RADIUS
from .skeletons import SkeletonDefinition


class AnnotationCanvas(QGraphicsView):
    """Canvas that displays the video frame and draggable keypoints."""

    keypoint_moved = Signal(int, float, float)
    keypoint_selected = Signal(int)
    canvas_double_clicked = Signal(float, float)
    keypoint_dropped = Signal(int, float, float)
    keypoint_drag_started = Signal(int)
    keypoint_move_finished = Signal(int, float, float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setBackgroundBrush(QColor("#111318"))
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._pixmap_item = QGraphicsPixmapItem()
        self._scene.addItem(self._pixmap_item)

        self._skeleton: SkeletonDefinition | None = None
        self._keypoint_items: list[KeypointItem] = []
        self._line_items: list[tuple[tuple[int, int], QGraphicsLineItem]] = []
        self._bridge_line_items: list[tuple[tuple[tuple[int, int], int], QGraphicsLineItem]] = []
        self._bridge_mid_line_items: list[
            tuple[tuple[int, tuple[int, int], int], tuple[QGraphicsLineItem, QGraphicsLineItem]]
        ] = []
        self._active_index = 0
        self._show_labels = True
        self._point_radius = DEFAULT_POINT_RADIUS
        self._line_width = DEFAULT_LINE_WIDTH
        self._space_pressed = False
        self._panning = False
        self._last_pan_point = QPoint()
        self._is_syncing = False
        self._show_frame_layer = True
        self._show_annotation_layer = True
        self._image_width = 1
        self._image_height = 1

    def set_skeleton(self, skeleton: SkeletonDefinition) -> None:
        self._skeleton = skeleton
        for item in self._keypoint_items:
            self._scene.removeItem(item)
        for _, line_item in self._line_items:
            self._scene.removeItem(line_item)
        for _, line_item in self._bridge_line_items:
            self._scene.removeItem(line_item)
        for _, line_items in self._bridge_mid_line_items:
            for line_item in line_items:
                self._scene.removeItem(line_item)
        self._keypoint_items.clear()
        self._line_items.clear()
        self._bridge_line_items.clear()
        self._bridge_mid_line_items.clear()

        for start, end in skeleton.connections:
            line_item = QGraphicsLineItem()
            line_item.setPen(QPen(QColor("#7bdff2"), self._line_width))
            line_item.setVisible(False)
            self._scene.addItem(line_item)
            self._line_items.append(((start, end), line_item))

        for shoulder_pair, hip_index in skeleton.bridge_connections:
            line_item = QGraphicsLineItem()
            line_item.setPen(QPen(QColor("#7bdff2"), self._line_width))
            line_item.setVisible(False)
            self._scene.addItem(line_item)
            self._bridge_line_items.append(((shoulder_pair, hip_index), line_item))

        for spine_index, shoulder_pair, hip_index in skeleton.bridge_mid_connections:
            upper_item = QGraphicsLineItem()
            upper_item.setPen(QPen(QColor("#7bdff2"), self._line_width))
            upper_item.setVisible(False)
            lower_item = QGraphicsLineItem()
            lower_item.setPen(QPen(QColor("#7bdff2"), self._line_width))
            lower_item.setVisible(False)
            self._scene.addItem(upper_item)
            self._scene.addItem(lower_item)
            self._bridge_mid_line_items.append(((spine_index, shoulder_pair, hip_index), (upper_item, lower_item)))

        for index, name in enumerate(skeleton.keypoints):
            item = KeypointItem(index=index, name=name, radius=self._effective_point_radius())
            item.set_show_label(self._show_labels)
            item.moved.connect(self._on_item_moved)
            item.selected.connect(self._on_item_selected)
            item.drag_started.connect(self.keypoint_drag_started)
            item.move_finished.connect(self.keypoint_move_finished)
            self._scene.addItem(item)
            self._keypoint_items.append(item)
        self.set_active_keypoint(0)
        self.set_layer_visibility(self._show_frame_layer, self._show_annotation_layer)
        self._update_point_radii()

    def set_frame_image(self, image_path: str | Path) -> None:
        pixmap = QPixmap(str(image_path))
        self._pixmap_item.setPixmap(pixmap)
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._pixmap_item.setVisible(self._show_frame_layer)
        self._image_width = max(1, pixmap.width())
        self._image_height = max(1, pixmap.height())
        self._update_point_radii()
        self._update_lines()

    def clear_image(self) -> None:
        self._pixmap_item.setPixmap(QPixmap())
        self._scene.setSceneRect(self._pixmap_item.boundingRect())
        self._image_width = 1
        self._image_height = 1
        self._update_point_radii()
        self._update_lines()

    def fit_content(self) -> None:
        if not self._pixmap_item.pixmap().isNull():
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def capture_view_state(self) -> dict[str, float | int]:
        return {
            "scale": round(self.transform().m11(), 6),
            "h": int(self.horizontalScrollBar().value()),
            "v": int(self.verticalScrollBar().value()),
        }

    def restore_view_state(self, state: dict | None) -> None:
        if not state:
            self.fit_content()
            return
        scale = float(state.get("scale", 1.0) or 1.0)
        h_value = int(state.get("h", 0) or 0)
        v_value = int(state.get("v", 0) or 0)
        self.resetTransform()
        if scale > 0:
            self.scale(scale, scale)

        def _apply_scrollbars() -> None:
            self.horizontalScrollBar().setValue(h_value)
            self.verticalScrollBar().setValue(v_value)

        QTimer.singleShot(0, _apply_scrollbars)

    def set_annotation(self, annotation: FrameAnnotation) -> None:
        self._is_syncing = True
        try:
            for index, state in enumerate(annotation.keypoints):
                if index >= len(self._keypoint_items):
                    break
                self._keypoint_items[index].apply_state(
                    state.x,
                    state.y,
                    state.v,
                    bool(state.contact),
                )
        finally:
            self._is_syncing = False
        self._update_lines()
        self.set_layer_visibility(self._show_frame_layer, self._show_annotation_layer)

    def set_active_keypoint(self, index: int) -> None:
        self._active_index = index
        for keypoint_item in self._keypoint_items:
            keypoint_item.set_active(keypoint_item.index == index)

    def set_show_labels(self, show_labels: bool) -> None:
        self._show_labels = show_labels
        for item in self._keypoint_items:
            item.set_show_label(show_labels)
        self.viewport().update()

    def _effective_point_radius(self) -> float:
        min_dimension = max(1, min(self._image_width, self._image_height))
        scale_factor = min(3.0, max(0.25, min_dimension / 1080.0))
        return max(1.0, self._point_radius * scale_factor)

    def _update_point_radii(self) -> None:
        effective_radius = self._effective_point_radius()
        for item in self._keypoint_items:
            item.set_radius(effective_radius)
        self.viewport().update()

    def set_point_radius(self, radius: float) -> None:
        self._point_radius = max(1.0, radius)
        self._update_point_radii()

    def set_line_width(self, line_width: float) -> None:
        self._line_width = line_width
        for _, line_item in self._line_items:
            pen = line_item.pen()
            pen.setWidthF(line_width)
            line_item.setPen(pen)
        for _, line_item in self._bridge_line_items:
            pen = line_item.pen()
            pen.setWidthF(line_width)
            line_item.setPen(pen)
        for _, line_items in self._bridge_mid_line_items:
            for line_item in line_items:
                pen = line_item.pen()
                pen.setWidthF(line_width)
                line_item.setPen(pen)
        self._update_lines()

    def set_layer_visibility(self, show_frame: bool, show_annotations: bool) -> None:
        self._show_frame_layer = show_frame
        self._show_annotation_layer = show_annotations
        self._pixmap_item.setVisible(show_frame)
        for item in self._keypoint_items:
            item.set_annotation_visible(show_annotations)
        self._update_lines()

    def center_on_keypoint(self, index: int) -> None:
        if 0 <= index < len(self._keypoint_items) and self._keypoint_items[index].isVisible():
            self.centerOn(self._keypoint_items[index])

    def _on_item_moved(self, index: int, x: float, y: float) -> None:
        self._update_lines()
        if not self._is_syncing:
            self.keypoint_moved.emit(index, x, y)

    def _on_item_selected(self, index: int) -> None:
        self.keypoint_selected.emit(index)

    def _spine_bridge_is_active(self, shoulder_pair: tuple[int, int], hip_index: int) -> bool:
        for (spine_index, current_shoulder_pair, current_hip_index), _ in self._bridge_mid_line_items:
            if current_shoulder_pair != shoulder_pair or current_hip_index != hip_index:
                continue
            if max(spine_index, shoulder_pair[0], shoulder_pair[1], hip_index) >= len(self._keypoint_items):
                continue
            spine_item = self._keypoint_items[spine_index]
            inner_item = self._keypoint_items[shoulder_pair[0]]
            outer_item = self._keypoint_items[shoulder_pair[1]]
            hip_item = self._keypoint_items[hip_index]
            if spine_item.isVisible() and inner_item.isVisible() and outer_item.isVisible() and hip_item.isVisible():
                return True
        return False

    def _center_hips_position(self) -> tuple[float, float] | None:
        if len(self._keypoint_items) <= 14:
            return None
        left_hip = self._keypoint_items[13]
        right_hip = self._keypoint_items[14]
        if not left_hip.isVisible() or not right_hip.isVisible():
            return None
        return (
            (left_hip.pos().x() + right_hip.pos().x()) / 2.0,
            (left_hip.pos().y() + right_hip.pos().y()) / 2.0,
        )

    def _normal_offset_break(
        self,
        axis_start_x: float,
        axis_start_y: float,
        axis_end_x: float,
        axis_end_y: float,
        reference_x: float,
        reference_y: float,
        anchor_x: float,
        anchor_y: float,
    ) -> tuple[float, float]:
        dx = axis_end_x - axis_start_x
        dy = axis_end_y - axis_start_y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return anchor_x, anchor_y
        dir_x = dx / length
        dir_y = dy / length
        normal_x = -dir_y
        normal_y = dir_x
        ref_dx = reference_x - axis_start_x
        ref_dy = reference_y - axis_start_y
        perpendicular = ref_dx * normal_x + ref_dy * normal_y
        if abs(perpendicular) <= 1e-6:
            perpendicular = math.hypot(ref_dx, ref_dy)
        return anchor_x + normal_x * perpendicular, anchor_y + normal_y * perpendicular

    def _compute_spine_break_point(
        self,
        center_shoulder_x: float,
        center_shoulder_y: float,
        shoulder_x: float,
        shoulder_y: float,
        spine_x: float,
        spine_y: float,
        hip_center_x: float,
        hip_center_y: float,
        hip_x: float,
        hip_y: float,
    ) -> tuple[float, float]:
        top_break = self._normal_offset_break(
            center_shoulder_x,
            center_shoulder_y,
            spine_x,
            spine_y,
            shoulder_x,
            shoulder_y,
            spine_x,
            spine_y,
        )
        bottom_break = self._normal_offset_break(
            spine_x,
            spine_y,
            hip_center_x,
            hip_center_y,
            hip_x,
            hip_y,
            spine_x,
            spine_y,
        )
        return (
            (top_break[0] + bottom_break[0]) / 2.0,
            (top_break[1] + bottom_break[1]) / 2.0,
        )

    def _update_lines(self) -> None:
        for (start, end), line_item in self._line_items:
            if start >= len(self._keypoint_items) or end >= len(self._keypoint_items):
                continue
            start_item = self._keypoint_items[start]
            end_item = self._keypoint_items[end]
            visible = self._show_annotation_layer and start_item.isVisible() and end_item.isVisible()
            line_item.setVisible(visible)
            if visible:
                line_item.setLine(
                    start_item.pos().x(),
                    start_item.pos().y(),
                    end_item.pos().x(),
                    end_item.pos().y(),
                )

        for ((shoulder_inner, shoulder_outer), hip_index), line_item in self._bridge_line_items:
            if max(shoulder_inner, shoulder_outer, hip_index) >= len(self._keypoint_items):
                continue
            inner_item = self._keypoint_items[shoulder_inner]
            outer_item = self._keypoint_items[shoulder_outer]
            hip_item = self._keypoint_items[hip_index]
            visible = (
                self._show_annotation_layer
                and inner_item.isVisible()
                and outer_item.isVisible()
                and hip_item.isVisible()
                and not self._spine_bridge_is_active((shoulder_inner, shoulder_outer), hip_index)
            )
            line_item.setVisible(visible)
            if visible:
                shoulder_x = (inner_item.pos().x() + outer_item.pos().x()) / 2.0
                shoulder_y = (inner_item.pos().y() + outer_item.pos().y()) / 2.0
                line_item.setLine(
                    shoulder_x,
                    shoulder_y,
                    hip_item.pos().x(),
                    hip_item.pos().y(),
                )

        for (spine_index, (shoulder_inner, shoulder_outer), hip_index), (upper_item, lower_item) in self._bridge_mid_line_items:
            if max(spine_index, shoulder_inner, shoulder_outer, hip_index) >= len(self._keypoint_items):
                upper_item.setVisible(False)
                lower_item.setVisible(False)
                continue
            spine_item = self._keypoint_items[spine_index]
            inner_item = self._keypoint_items[shoulder_inner]
            outer_item = self._keypoint_items[shoulder_outer]
            hip_item = self._keypoint_items[hip_index]
            visible = (
                self._show_annotation_layer
                and spine_item.isVisible()
                and inner_item.isVisible()
                and outer_item.isVisible()
                and hip_item.isVisible()
            )
            upper_item.setVisible(visible)
            lower_item.setVisible(visible)
            if visible:
                center_hips = self._center_hips_position() or (hip_item.pos().x(), hip_item.pos().y())
                shoulder_x = (inner_item.pos().x() + outer_item.pos().x()) / 2.0
                shoulder_y = (inner_item.pos().y() + outer_item.pos().y()) / 2.0
                break_x, break_y = self._compute_spine_break_point(
                    inner_item.pos().x(),
                    inner_item.pos().y(),
                    shoulder_x,
                    shoulder_y,
                    spine_item.pos().x(),
                    spine_item.pos().y(),
                    center_hips[0],
                    center_hips[1],
                    hip_item.pos().x(),
                    hip_item.pos().y(),
                )
                upper_item.setLine(shoulder_x, shoulder_y, break_x, break_y)
                lower_item.setLine(break_x, break_y, hip_item.pos().x(), hip_item.pos().y())

    def wheelEvent(self, event: QWheelEvent) -> None:
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pressed = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Space:
            self._space_pressed = False
            if not self._panning:
                self.viewport().unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton or (
            self._space_pressed and event.button() == Qt.MouseButton.LeftButton
        ):
            self._panning = True
            self._last_pan_point = event.pos()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._panning:
            delta = event.pos() - self._last_pan_point
            self._last_pan_point = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._panning and (
            event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.LeftButton
        ):
            self._panning = False
            if self._space_pressed:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            self.fit_content()
            event.accept()
            return
        scene_pos = self.mapToScene(event.position().toPoint())
        self.canvas_double_clicked.emit(scene_pos.x(), scene_pos.y())
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(KEYPOINT_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(KEYPOINT_MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasFormat(KEYPOINT_MIME_TYPE):
            try:
                index = int(bytes(event.mimeData().data(KEYPOINT_MIME_TYPE)).decode("utf-8"))
            except ValueError:
                event.ignore()
                return
            scene_pos = self.mapToScene(event.position().toPoint())
            self.keypoint_dropped.emit(index, scene_pos.x(), scene_pos.y())
            event.acceptProposedAction()
            return
        super().dropEvent(event)
