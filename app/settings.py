"""Application-wide settings and UI constants."""

from __future__ import annotations

from pathlib import Path


def _load_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "1.0.0"
    return version or "1.0.0"


APP_NAME = "WS3D Pose Annotator"
APP_VERSION = _load_version()
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"
PROJECT_EXTENSION = ".poseproj.json"
AUTOSAVE_INTERVAL_MS = 60_000
DEFAULT_POINT_RADIUS = 4.0
DEFAULT_LINE_WIDTH = 2.0
SUPPORTED_VIDEO_FILTER = "Videos (*.mp4 *.mov *.avi *.mkv)"
SUPPORTED_IMAGE_FILTER = "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)"
SUPPORTED_MEDIA_FILTER = "Midias (*.mp4 *.mov *.avi *.mkv *.png *.jpg *.jpeg *.bmp *.webp)"
MAX_RECENT_PROJECTS = 8

DARK_STYLESHEET = """
QWidget {
    background-color: #1e1f24;
    color: #f4f4f1;
    font-size: 11pt;
}
QMainWindow::separator {
    background: #34353d;
    width: 1px;
    height: 1px;
}
QMenuBar, QMenu, QToolTip {
    background-color: #262831;
    color: #f4f4f1;
}
QMenu::item:selected, QMenuBar::item:selected {
    background-color: #3e5c76;
}
QPushButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #2a2d38;
    border: 1px solid #444857;
    border-radius: 4px;
    padding: 5px;
}
QPushButton:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border-color: #6ea8d9;
}
QSlider::groove:horizontal {
    background: #373b46;
    height: 8px;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #d4a373;
    width: 16px;
    margin: -5px 0;
    border-radius: 8px;
}
QTableWidget {
    background-color: #23252d;
    alternate-background-color: #2a2d36;
    gridline-color: #343743;
    selection-background-color: #3e5c76;
}
QHeaderView::section {
    background-color: #2a2d38;
    padding: 6px;
    border: none;
    border-bottom: 1px solid #3b3e4a;
}
QLabel[role="muted"] {
    color: #c9ced8;
}
QGroupBox {
    border: 1px solid #3c3f4b;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QStatusBar {
    background-color: #262831;
}
"""
