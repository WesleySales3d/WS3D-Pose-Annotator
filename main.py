"""Application entrypoint."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app.settings import APP_NAME, APP_TITLE, APP_VERSION, DARK_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
