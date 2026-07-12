"""Background serial reader: STM32 VCP -> Frame objects via Qt signals."""

from __future__ import annotations

import serial
from PyQt6 import QtCore
from serial.tools import list_ports

from core import config
from .protocol import FrameParser

# ST-Link VCP enumerates with STMicroelectronics' USB vendor ID.
ST_VID = 0x0483
READ_CHUNK = 4096
RETRY_DELAY_S = 1.0


def list_candidate_ports() -> list[str]:
    """Serial ports sorted so ST-Link boards come first."""
    ports = list(list_ports.comports())
    ports.sort(key=lambda p: (p.vid != ST_VID, p.device))
    return [p.device for p in ports]


class SerialReader(QtCore.QThread):
    """Owns the serial port; emits one signal per complete frame.

    The thread keeps retrying on I/O errors (board unplugged/replugged)
    until ``stop()`` is called.
    """

    frameReceived = QtCore.pyqtSignal(object)   # protocol.Frame
    statusChanged = QtCore.pyqtSignal(str)
    connectionChanged = QtCore.pyqtSignal(bool)

    def __init__(self, port: str, baud: int = config.SERIAL_BAUD, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: N802 (Qt naming)
        parser = FrameParser()
        while not self._stop:
            try:
                with serial.Serial(self._port, self._baud, timeout=0.5) as ser:
                    self.connectionChanged.emit(True)
                    self.statusChanged.emit(f"Connected to {self._port} @ {self._baud}")
                    ser.reset_input_buffer()
                    while not self._stop:
                        data = ser.read(READ_CHUNK)
                        if not data:
                            continue
                        for frame in parser.feed(data):
                            self.frameReceived.emit(frame)
            except (serial.SerialException, OSError) as exc:
                self.connectionChanged.emit(False)
                if self._stop:
                    break
                self.statusChanged.emit(f"Serial error on {self._port}: {exc} — retrying")
                self.msleep(int(RETRY_DELAY_S * 1000))
        self.connectionChanged.emit(False)
