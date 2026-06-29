"""Results panel: ideal-vs-measured comparison table and THD bar charts."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

from core.models import Measurements
from . import theme
from .widgets import Panel

# (attribute, label, unit, format)
METRICS = [
    ("vrms", "V rms", "V", "{:.2f}"),
    ("irms", "I rms", "A", "{:.3f}"),
    ("frequency", "Frequency", "Hz", "{:.3f}"),
    ("p_total", "P total", "W", "{:.1f}"),
    ("q_total", "Q total", "VAR", "{:.1f}"),
    ("s_total", "S total", "VA", "{:.1f}"),
    ("tpf", "TPF", "", "{:.4f}"),
    ("p_fund", "P fund", "W", "{:.1f}"),
    ("q_fund", "Q fund", "VAR", "{:.1f}"),
    ("s_fund", "S fund", "VA", "{:.1f}"),
    ("phi_deg", "Phi", "deg", "{:.2f}"),
    ("dpf", "DPF", "", "{:.4f}"),
    ("thd_v", "THD V", "%", "{:.2f}"),
    ("thd_i", "THD I", "%", "{:.2f}"),
]


class ResultsPanel(Panel):
    def __init__(self, parent=None):
        super().__init__("MEASUREMENTS  —  DSP vs IDEAL", parent)

        self.table = QtWidgets.QTableWidget(len(METRICS), 4)
        self.table.setHorizontalHeaderLabels(["Parameter", "Measured", "Ideal", "Error"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            hdr.setSectionResizeMode(c, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Reserve enough height to show every metric row without scrolling.
        self.table.setMinimumHeight(len(METRICS) * 22 + 30)
        self.table.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                 QtWidgets.QSizePolicy.Policy.Fixed)
        self.table.setFixedHeight(len(METRICS) * 22 + 28)
        for row, (_a, label, unit, _f) in enumerate(METRICS):
            name = f"{label} [{unit}]" if unit else label
            self.table.setItem(row, 0, self._cell(name, theme.TEXT_DIM))
            for c in (1, 2, 3):
                self.table.setItem(row, c, self._cell("--", theme.TEXT))
        self.add(self.table)

        self.add(self._sec("HARMONIC SPECTRUM (normalized)"))
        self.thd_plot = pg.PlotWidget()
        self.thd_plot.showGrid(x=True, y=True, alpha=0.2)
        self.thd_plot.setLabel("bottom", "Harmonic order")
        self.thd_plot.setLabel("left", "Amplitude")
        self.thd_plot.getAxis("left").setTextPen(theme.TEXT_DIM)
        self.thd_plot.getAxis("bottom").setTextPen(theme.TEXT_DIM)
        self.thd_plot.setMenuEnabled(False)
        self.thd_plot.setMouseEnabled(x=False, y=False)
        self.thd_plot.setYRange(0, 1.0)
        self.thd_plot.setMinimumHeight(120)
        self._v_bars = pg.BarGraphItem(x=[], height=[], width=0.4, brush=theme.V_COLOR)
        self._i_bars = pg.BarGraphItem(x=[], height=[], width=0.4, brush=theme.I_COLOR)
        self.thd_plot.addItem(self._v_bars)
        self.thd_plot.addItem(self._i_bars)
        self.add(self.thd_plot, 1)

    @staticmethod
    def _cell(text: str, color: str) -> QtWidgets.QTableWidgetItem:
        item = QtWidgets.QTableWidgetItem(text)
        item.setForeground(QtGui.QColor(color))
        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter
                              | QtCore.Qt.AlignmentFlag.AlignRight)
        return item

    @staticmethod
    def _sec(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def update_results(self, measured: Measurements, reference: Measurements) -> None:
        for row, (attr, _label, _unit, fmt) in enumerate(METRICS):
            mv = getattr(measured, attr)
            rv = getattr(reference, attr)
            self.table.item(row, 1).setText(fmt.format(mv))
            self.table.item(row, 2).setText(fmt.format(rv))
            if abs(rv) > 1e-9:
                err = 100.0 * (mv - rv) / rv
                self.table.item(row, 3).setText(f"{err:+.2f}%")
                color = (theme.GREEN if abs(err) < 1.0
                         else theme.AMBER if abs(err) < 5.0 else theme.RED)
            else:
                self.table.item(row, 3).setText("--")
                color = theme.TEXT_DIM
            self.table.item(row, 3).setForeground(QtGui.QColor(color))

        self._update_bars(measured)

    def _update_bars(self, m: Measurements) -> None:
        v = np.asarray(m.v_harmonics[:15]) if m.v_harmonics else np.array([])
        i = np.asarray(m.i_harmonics[:15]) if m.i_harmonics else np.array([])
        n = max(len(v), len(i))
        if n == 0:
            return
        orders = np.arange(1, n + 1)
        v = np.pad(v, (0, n - len(v)))
        i = np.pad(i, (0, n - len(i)))
        self._v_bars.setOpts(x=orders - 0.2, height=v, width=0.4)
        self._i_bars.setOpts(x=orders + 0.2, height=i, width=0.4)
        self.thd_plot.setXRange(0.5, n + 0.5)
