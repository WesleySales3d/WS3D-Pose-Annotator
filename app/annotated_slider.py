"""Slider with clickable markers for annotated frames."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class AnnotatedTimelineSlider(QSlider):
    """Draws small markers above the slider groove and lets them be clicked."""

    marker_clicked = Signal(int)

    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self._markers: list[int] = []

    def set_markers(self, markers: list[int]) -> None:
        self._markers = sorted(set(markers))
        self.update()

    def _value_to_pos(self, value: int) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        handle = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            option,
            QStyle.SubControl.SC_SliderHandle,
            self,
        )
        slider_min = groove.x()
        slider_max = groove.right() - handle.width() + 1
        handle_left = QStyle.sliderPositionFromValue(
            self.minimum(),
            self.maximum(),
            value,
            slider_max - slider_min,
        ) + slider_min
        return int(handle_left + handle.width() / 2)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._markers or self.maximum() <= self.minimum():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#00f5a0"))
        top_y = 2
        for value in self._markers:
            x = self._value_to_pos(value)
            painter.drawRoundedRect(x - 2, top_y, 4, 8, 1.5, 1.5)
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._markers:
            for marker in self._markers:
                marker_x = self._value_to_pos(marker)
                if abs(event.position().x() - marker_x) <= 6:
                    self.marker_clicked.emit(marker)
                    event.accept()
                    return
        super().mousePressEvent(event)
