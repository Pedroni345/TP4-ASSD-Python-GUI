"""Entry point for the TP4-ASSD power-analyzer simulator GUI."""

from __future__ import annotations

import sys

from PyQt6 import QtWidgets

from ui import theme
from ui.main_window import MainWindow


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
