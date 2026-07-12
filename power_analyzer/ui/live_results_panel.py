"""Live results: measured values only (no analytic reference available)."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

from core.models import Measurements
from . import theme
from .results_panel import METRICS
from .widgets import Panel


class LiveResultsPanel(Panel):
    """Two-column table (parameter / averaged value) + harmonic spectrum."""

    def __init__(self, parent=None):
        super().__init__("MEASUREMENTS  —  live (averaged)", parent)

        self.table = QtWidgets.QTableWidget(len(METRICS), 2)
        self.table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setFixedHeight(len(METRICS) * 22 + 28)
        for row, (_a, label, unit, _f) in enumerate(METRICS):
            name = f"{label} [{unit}]" if unit else label
            self.table.setItem(row, 0, self._cell(name, theme.TEXT_DIM))
            self.table.setItem(row, 1, self._cell("--", theme.TEXT))
        self.add(self.table)

        lbl = QtWidgets.QLabel("HARMONIC SPECTRUM (normalized)")
        lbl.setObjectName("sectionTitle")
        self.add(lbl)

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

    def update_results(self, m: Measurements) -> None:
        for row, (attr, _label, _unit, fmt) in enumerate(METRICS):
            self.table.item(row, 1).setText(fmt.format(getattr(m, attr)))

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
