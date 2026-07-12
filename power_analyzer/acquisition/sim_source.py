"""Fake frame source: exercises the live GUI without the STM32 attached.

Generates the notebook's default v(t)/i(t) directly at the MCU sample rate,
scales through the fixed PGA ranges and quantizes to int16 codes — the same
thing the hardware chain does before the snapshot hits the UART.
"""

from __future__ import annotations

import numpy as np
from PyQt6 import QtCore

from core import config
from core.models import SignalSpec
from dsp import signal_gen
from .protocol import Frame


def default_live_spec() -> SignalSpec:
    """Notebook default signal, with the current scaled to fit the fixed
    G16 hardware range (+/-3.13 A) so the simulated channel doesn't clip."""
    spec = SignalSpec.default()
    third = [0.0] * (config.MAX_HARMONIC - 1)
    third[1] = 0.5
    return spec.with_current(fundamental=2.5, dc_offset=0.2, noise_std=0.1,
                             harmonic_amps=tuple(third))


def synth_frame(spec: SignalSpec, t_offset: float,
                v_range: float, i_range: float) -> Frame:
    duration = config.FRAME_SAMPLES / config.FS_MCU
    t, v, i = signal_gen.generate(spec, duration, fs=config.FS_MCU,
                                  t_offset=t_offset)
    t = t[: config.FRAME_SAMPLES]
    v = v[: config.FRAME_SAMPLES]
    i = i[: config.FRAME_SAMPLES]

    def to_codes(x: np.ndarray, rng: float) -> np.ndarray:
        scaled = np.clip(x / rng, -1.0, 1.0) * (config.ADC_FULL_SCALE - 1)
        return scaled.astype(np.int16)

    return Frame(v_codes=to_codes(v, v_range), i_codes=to_codes(i, i_range))


class SimSource(QtCore.QObject):
    """Emits synthetic frames on a timer, mimicking the 1 Hz MCU stream."""

    frameReceived = QtCore.pyqtSignal(object)
    statusChanged = QtCore.pyqtSignal(str)
    connectionChanged = QtCore.pyqtSignal(bool)

    def __init__(self, interval_ms: int = 1000, parent=None):
        super().__init__(parent)
        self._spec = default_live_spec()
        self._t_offset = 0.0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()
        self.connectionChanged.emit(True)
        self.statusChanged.emit("Simulated source (no hardware)")
        self._tick()

    def stop(self) -> None:
        self._timer.stop()
        self.connectionChanged.emit(False)

    # QThread-compat no-ops so LiveWindow can treat both sources alike.
    def wait(self, *_args) -> bool:
        return True

    def _tick(self) -> None:
        frame = synth_frame(
            self._spec, self._t_offset,
            config.VOLTAGE_GAINS[config.LIVE_VOLTAGE_GAIN],
            config.CURRENT_GAINS[config.LIVE_CURRENT_GAIN],
        )
        self._t_offset += config.FRAME_SAMPLES / config.FS_MCU
        self.frameReceived.emit(frame)
