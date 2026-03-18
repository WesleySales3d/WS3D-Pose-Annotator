"""Annotation canvas based on QGraphicsView."""

from __future__ import annotations

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
        self._keypoint_items.clear()
        self._line_items.clear()
        self._bridge_line_items.clear()

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
            )
            line_item.setVisible(visible)
            if visible:
                shoulder_x = (inner_item.pos().x() + outer_item.pos().x()) / 2
                shoulder_y = (inner_item.pos().y() + outer_item.pos().y()) / 2
                line_item.setLine(
                    shoulder_x,
                    shoulder_y,
                    hip_item.pos().x(),
                    hip_item.pos().y(),
                )

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
