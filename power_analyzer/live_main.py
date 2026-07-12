"""Entry point for the live visualizer (STM32 over USB serial).

Usage:
    python live_main.py                # auto-detect the ST-Link port
    python live_main.py --port /dev/ttyACM0
    python live_main.py --sim          # no hardware: synthetic frames
"""

from __future__ import annotations

import argparse
import sys

from PyQt6 import QtWidgets

from ui import theme
from ui.live_window import LiveWindow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=None,
                        help="serial port (default: auto-detect ST-Link)")
    parser.add_argument("--sim", action="store_true",
                        help="use a synthetic frame source instead of hardware")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(theme.STYLESHEET)
    window = LiveWindow(port=args.port, simulate=args.sim)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
