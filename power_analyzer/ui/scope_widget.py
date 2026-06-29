"""pyqtgraph oscilloscope: stacked V and I plots with per-stage tap traces."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtWidgets

from core.models import StageTraces
from dsp.pipeline import ScopeResult
from . import theme

# Tap points the user can overlay. (key, label, is_digital_rate)
STAGES = [
    ("raw", "Analog In", False),
    ("antialiased", "Anti-Alias", False),
    ("adc", "ADC (quantized)", True),
    ("highpass", "High-Pass", True),
]
STAGE_COLORS = {
    "raw": theme.TEXT_DIM,
    "antialiased": theme.BLUE,
    "adc": theme.AMBER,
    "highpass": None,   # uses channel color (cyan / green)
}


class _ChannelPlot(pg.PlotWidget):
    """A single oscilloscope plot for one channel."""

    def __init__(self, ylabel: str, channel_color: str, parent=None):
        super().__init__(parent)
        self.channel_color = channel_color
        self.showGrid(x=True, y=True, alpha=0.25)
        self.setLabel("bottom", "Time", units="ms")
        self.setLabel("left", ylabel)
        self.getAxis("left").setPen(theme.GRID)
        self.getAxis("bottom").setPen(theme.GRID)
        self.getAxis("left").setTextPen(theme.TEXT_DIM)
        self.getAxis("bottom").setTextPen(theme.TEXT_DIM)
        self.setMenuEnabled(False)
        self.setMouseEnabled(x=False, y=True)

        self._curves: dict[str, pg.PlotDataItem] = {}
        self._glow: dict[str, pg.PlotDataItem] = {}
        for key, _label, _dig in STAGES:
            color = STAGE_COLORS[key] or channel_color
            # Soft glow underlay for the bright high-pass trace.
            if key == "highpass":
                glow = self.plot([], [], pen=theme.faint_pen(color, 6))
                self._glow[key] = glow
            width = 1.0 if key in ("raw",) else 1.6
            pen = (theme.faint_pen(color, 1.2) if key == "raw"
                   else theme.trace_pen(color, width))
            curve = self.plot([], [], pen=pen)
            if key == "highpass":
                curve.setFillLevel(0)
                curve.setBrush(theme.fill_brush(color, 40))
            self._curves[key] = curve

    def update_traces(self, tr: StageTraces, visible: set[str]) -> None:
        t_a = tr.t_analog * 1000.0
        t_d = tr.t_digital * 1000.0
        data = {
            "raw": (t_a, tr.raw),
            "antialiased": (t_a, tr.antialiased),
            "adc": (t_d, tr.adc),
            "highpass": (t_d, tr.highpass),
        }
        for key, _label, _dig in STAGES:
            curve = self._curves[key]
            if key in visible:
                x, y = data[key]
                curve.setData(x, y)
                curve.setVisible(True)
                if key in self._glow:
                    self._glow[key].setData(x, y)
                    self._glow[key].setVisible(True)
            else:
                curve.setVisible(False)
                if key in self._glow:
                    self._glow[key].setVisible(False)


class ScopeWidget(QtWidgets.QWidget):
    """Two stacked channel plots plus stage-tap toggle buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Stage toggle bar.
        bar = QtWidgets.QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(self._tag("PROBE:"))
        self._buttons: dict[str, QtWidgets.QPushButton] = {}
        default_on = {"antialiased", "highpass"}
        for key, label, _dig in STAGES:
            btn = QtWidgets.QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key in default_on)
            color = STAGE_COLORS[key] or theme.CYAN
            btn.setStyleSheet(f"QPushButton:checked {{ color: {color}; border-color: {color}; }}")
            btn.clicked.connect(self._refresh_visibility)
            self._buttons[key] = btn
            bar.addWidget(btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.v_plot = _ChannelPlot("Voltage [V]", theme.V_COLOR)
        self.i_plot = _ChannelPlot("Current [A]", theme.I_COLOR)
        self.i_plot.setXLink(self.v_plot)
        layout.addWidget(self.v_plot, 1)
        layout.addWidget(self.i_plot, 1)

        self._last: ScopeResult | None = None

    @staticmethod
    def _tag(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("dimText")
        return lbl

    def _visible(self) -> set[str]:
        return {k for k, b in self._buttons.items() if b.isChecked()}

    def _refresh_visibility(self) -> None:
        if self._last is not None:
            self.update_result(self._last)

    def update_result(self, result: ScopeResult) -> None:
        self._last = result
        vis = self._visible()
        self.v_plot.update_traces(result.voltage, vis)
        self.i_plot.update_traces(result.current, vis)
