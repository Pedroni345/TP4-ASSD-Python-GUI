"""Live scope: the V and I traces of the latest MCU frame."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtWidgets

from . import theme


class _FramePlot(pg.PlotWidget):
    def __init__(self, ylabel: str, color: str, parent=None):
        super().__init__(parent)
        self.setBackground(theme.BG_PANEL)
        self.showGrid(x=True, y=True, alpha=0.25)
        self.setLabel("left", ylabel)
        self.setLabel("bottom", "t [ms]")
        self.getAxis("left").setTextPen(theme.TEXT_DIM)
        self.getAxis("bottom").setTextPen(theme.TEXT_DIM)
        self.setMenuEnabled(False)
        self._curve = self.plot([], [], pen=theme.trace_pen(color))

    def update_trace(self, t: np.ndarray, y: np.ndarray) -> None:
        self._curve.setData(t * 1e3, y)


class LiveScope(QtWidgets.QWidget):
    """Two stacked plots sharing the frame time axis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.v_plot = _FramePlot("V [V]", theme.V_COLOR)
        self.i_plot = _FramePlot("I [A]", theme.I_COLOR)
        self.i_plot.setXLink(self.v_plot)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.v_plot, 1)
        lay.addWidget(self.i_plot, 1)

    def update_frame(self, t: np.ndarray, v: np.ndarray, i: np.ndarray) -> None:
        self.v_plot.update_trace(t, v)
        self.i_plot.update_trace(t, i)
