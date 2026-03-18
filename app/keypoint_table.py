"""Drag-enabled table for keypoints."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTableWidget


KEYPOINT_MIME_TYPE = "application/x-pose-keypoint-index"


class KeypointTable(QTableWidget):
    """QTableWidget that can drag the selected keypoint onto the canvas."""

    def __init__(self, rows: int = 0, columns: int = 0, parent=None) -> None:
        super().__init__(rows, columns, parent)
        self.setDragEnabled(True)
        self._row_keypoint_indices: list[int] = []

    def set_keypoint_indices_for_rows(self, indices: list[int]) -> None:
        self._row_keypoint_indices = list(indices)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:
        del supported_actions
        current_row = self.currentRow()
        if current_row < 0:
            return
        keypoint_index = (
            self._row_keypoint_indices[current_row]
            if 0 <= current_row < len(self._row_keypoint_indices)
            else current_row
        )
        mime_data = QMimeData()
        mime_data.setData(KEYPOINT_MIME_TYPE, str(keypoint_index).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)
