"""Graphics item used for draggable keypoints."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject


class KeypointItem(QGraphicsObject):
    """Interactive keypoint marker."""

    moved = Signal(int, float, float)
    selected = Signal(int)
    drag_started = Signal(int)
    move_finished = Signal(int, float, float)

    def __init__(self, index: int, name: str, radius: float = 7.0) -> None:
        super().__init__()
        self.index = index
        self.name = name
        self._radius = radius
        self._visibility_value = 0
        self._contact = False
        self._active = False
        self._show_label = True
        self._state_visible = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setVisible(False)

    def boundingRect(self) -> QRectF:
        pad = 28 if self._show_label else 6
        radius = self._radius + pad
        return QRectF(-radius, -radius, radius * 2.5, radius * 2.0)

    def set_radius(self, radius: float) -> None:
        self.prepareGeometryChange()
        self._radius = radius
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        self.update()

    def set_show_label(self, show_label: bool) -> None:
        self.prepareGeometryChange()
        self._show_label = show_label
        self.update()

    def apply_state(self, x: float, y: float, visibility_value: int, contact: bool = False) -> None:
        self._visibility_value = visibility_value
        self._contact = contact
        self._state_visible = visibility_value > 0
        self.setVisible(self._state_visible)
        if visibility_value > 0:
            self.setPos(QPointF(x, y))
        self.update()

    def set_annotation_visible(self, visible: bool) -> None:
        self.setVisible(self._state_visible and visible)

    def _fill_color(self) -> QColor:
        if self._visibility_value == 2:
            return QColor("#ff6b6b")
        if self._visibility_value == 1:
            return QColor("#ffd166")
        return QColor("#8f949e")

    def paint(self, painter: QPainter, option, widget=None) -> None:
        del option, widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outline = QColor("#ffffff") if self._active else QColor("#111111")
        outline_width = 2.6 if self._active else 1.6
        painter.setPen(QPen(outline, outline_width))
        painter.setBrush(self._fill_color())
        painter.drawEllipse(QRectF(-self._radius, -self._radius, self._radius * 2, self._radius * 2))
        if self._contact:
            painter.setPen(QPen(QColor("#00f5a0"), 2.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            inner_radius = max(2.0, self._radius * 0.55)
            painter.drawRect(
                QRectF(-inner_radius, -inner_radius, inner_radius * 2, inner_radius * 2)
            )
        if self._show_label:
            painter.setPen(QColor("#f2f2f2"))
            painter.drawText(QPointF(self._radius + 4, -self._radius - 2), self.name)

    def mousePressEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.selected.emit(self.index)
        self.drag_started.emit(self.index)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        position = self.pos()
        self.move_finished.emit(self.index, position.x(), position.y())
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene() is not None:
            position = value
            if isinstance(position, QPointF):
                rect = self.scene().sceneRect()
                clamped_x = min(max(position.x(), rect.left()), rect.right())
                clamped_y = min(max(position.y(), rect.top()), rect.bottom())
                return QPointF(clamped_x, clamped_y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.isVisible():
            position = self.pos()
            self.moved.emit(self.index, position.x(), position.y())
        return super().itemChange(change, value)
