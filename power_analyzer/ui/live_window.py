"""Live main window: STM32 serial stream -> scope + averaged measurements.

Unlike the simulator window there is no signal editor and no gain control:
the PGA281 gains are fixed by the firmware at boot, so the only front-end
inputs here are which serial port to read and how the fixed ranges map ADC
codes back to volts/amps.
"""

from __future__ import annotations

import time
from collections import deque

from PyQt6 import QtCore, QtWidgets

from acquisition import serial_reader
from acquisition.protocol import Frame
from acquisition.serial_reader import SerialReader
from acquisition.sim_source import SimSource
from core import config
from dsp import live
from . import theme
from .live_results_panel import LiveResultsPanel
from .live_scope import LiveScope
from .widgets import FillBar, Panel


class LiveWindow(QtWidgets.QMainWindow):
    def __init__(self, port: str | None = None, simulate: bool = False):
        super().__init__()
        self.setWindowTitle("TP4-ASSD  —  Power Analyzer (live, STM32)")
        self.resize(1300, 800)

        self._source: SerialReader | SimSource | None = None
        self._history: deque = deque(maxlen=config.LIVE_AVG_FRAMES)
        self._n_frames = 0
        self._last_frame_time: float | None = None

        # --- connection / front-end panel (left) ---
        conn = Panel("ACQUISITION  —  STM32 link")
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

        self.port_combo = QtWidgets.QComboBox()
        self.port_combo.setEditable(True)
        refresh_btn = QtWidgets.QPushButton("Rescan")
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row = QtWidgets.QHBoxLayout()
        port_row.addWidget(self.port_combo, 1)
        port_row.addWidget(refresh_btn)
        form.addRow("Port", port_row)

        self.connect_btn = QtWidgets.QPushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        form.addRow("", self.connect_btn)

        self.v_range_combo = QtWidgets.QComboBox()
        self.v_range_combo.addItems(list(config.VOLTAGE_GAINS))
        self.v_range_combo.setCurrentText(config.LIVE_VOLTAGE_GAIN)
        form.addRow("V range (PGA)", self.v_range_combo)

        self.i_range_combo = QtWidgets.QComboBox()
        self.i_range_combo.addItems(list(config.CURRENT_GAINS))
        self.i_range_combo.setCurrentText(config.LIVE_CURRENT_GAIN)
        form.addRow("I range (PGA)", self.i_range_combo)

        self.avg_spin = QtWidgets.QSpinBox()
        self.avg_spin.setRange(1, 60)
        self.avg_spin.setValue(config.LIVE_AVG_FRAMES)
        self.avg_spin.valueChanged.connect(self._on_avg_changed)
        form.addRow("Avg frames", self.avg_spin)

        wrap = QtWidgets.QWidget()
        wrap.setLayout(form)
        conn.add(wrap)

        conn.add(self._sec("ADC RANGE FILL"))
        self.v_fill = FillBar()
        self.i_fill = FillBar()
        fill_form = QtWidgets.QFormLayout()
        fill_form.addRow("V", self.v_fill)
        fill_form.addRow("I", self.i_fill)
        fill_wrap = QtWidgets.QWidget()
        fill_wrap.setLayout(fill_form)
        conn.add(fill_wrap)
        conn.add(QtWidgets.QWidget(), 1)  # spacer

        # --- scope (center) ---
        self.scope = LiveScope()
        scope_panel = Panel("LATEST FRAME  —  512 samples @ 10 kHz (~2.5 cycles)")
        scope_panel.add(self.scope, 1)

        # --- results (right) ---
        self.results = LiveResultsPanel()

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(conn)
        splitter.addWidget(scope_panel)
        splitter.addWidget(self.results)
        splitter.setSizes([280, 640, 380])

        root = QtWidgets.QWidget()
        root.setObjectName("root")
        lay = QtWidgets.QHBoxLayout(root)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(splitter)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Disconnected")

        self._simulate = simulate
        self._refresh_ports()
        if port:
            self.port_combo.setCurrentText(port)
        if simulate or port or self.port_combo.currentText():
            self._toggle_connection()

    @staticmethod
    def _sec(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    # --- connection management ---
    def _refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItems(serial_reader.list_candidate_ports())
        if current:
            self.port_combo.setCurrentText(current)

    def _toggle_connection(self) -> None:
        if self._source is not None:
            self._disconnect_source()
            return

        if self._simulate:
            source: SerialReader | SimSource = SimSource(parent=self)
        else:
            port = self.port_combo.currentText().strip()
            if not port:
                self.statusBar().showMessage(
                    "No serial port found — plug in the board and Rescan, "
                    "or run with --sim")
                return
            source = SerialReader(port)

        source.frameReceived.connect(self._on_frame)
        source.statusChanged.connect(self.statusBar().showMessage)
        source.connectionChanged.connect(self._on_connection)
        self._source = source
        source.start()
        self.connect_btn.setText("Disconnect")

    def _disconnect_source(self) -> None:
        if self._source is None:
            return
        self._source.stop()
        self._source.wait(2000)
        self._source = None
        self.connect_btn.setText("Connect")
        self.statusBar().showMessage("Disconnected")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._disconnect_source()
        super().closeEvent(event)

    def _on_connection(self, up: bool) -> None:
        color = theme.GREEN if up else theme.RED
        self.statusBar().setStyleSheet(f"color: {color};")

    def _on_avg_changed(self, n: int) -> None:
        self._history = deque(self._history, maxlen=n)

    # --- frame handling ---
    def _on_frame(self, frame: Frame) -> None:
        v_range = config.VOLTAGE_GAINS[self.v_range_combo.currentText()]
        i_range = config.CURRENT_GAINS[self.i_range_combo.currentText()]
        try:
            result = live.process_frame(frame, v_range, i_range)
        except Exception as exc:  # keep the UI alive on a corrupt frame
            self.statusBar().showMessage(f"DSP error: {exc}")
            return

        self._n_frames += 1
        self._last_frame_time = time.monotonic()
        self._history.append(result.measurements)
        avg = live.average_measurements(list(self._history))

        self.scope.update_frame(result.t, result.v, result.i)
        self.results.update_results(avg)
        self.v_fill.set_value(result.v_fill_pct, result.v_clipped)
        self.i_fill.set_value(result.i_fill_pct, result.i_clipped)

        clip = "  |  CLIPPING" if (result.v_clipped or result.i_clipped) else ""
        note = ("" if result.measurements.n_blocks
                else "  |  no zero-crossings in frame")
        self.statusBar().showMessage(
            f"frames={self._n_frames}   "
            f"f={avg.frequency:.2f} Hz   Vrms={avg.vrms:.2f} V   "
            f"Irms={avg.irms:.3f} A   P={avg.p_total:.1f} W{clip}{note}")
