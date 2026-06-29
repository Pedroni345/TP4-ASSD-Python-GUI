"""Main window: assembles panels and drives the live scope + DSP timers."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from core.models import FrontEndConfig, SignalSpec
from dsp import pipeline
from . import theme
from .block_diagram import BlockDiagram
from .frontend_panel import FrontEndPanel
from .harmonic_editor import HarmonicEditor
from .results_panel import ResultsPanel
from .scope_widget import ScopeWidget
from .widgets import Panel

SCOPE_FPS = 40
SCOPE_CYCLES = 4            # cycles shown on screen
SCROLL_FRACTION = 0.015    # fraction of a cycle the trace drifts per frame
MEAS_INTERVAL_MS = 600     # DSP measurement refresh period


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TP4-ASSD  —  Power Analyzer Simulator")
        self.resize(1500, 900)

        self._spec: SignalSpec = SignalSpec.default()
        self._fe: FrontEndConfig = FrontEndConfig()
        self._t_offset = 0.0
        self._meas_dirty = True

        # --- panels ---
        self.editor = HarmonicEditor()
        self.scope = ScopeWidget()
        self.frontend = FrontEndPanel()
        self.results = ResultsPanel()
        self.chain = BlockDiagram()

        scope_panel = QtWidgets.QFrame()
        scope_panel.setObjectName("panel")
        sp_lay = QtWidgets.QVBoxLayout(scope_panel)
        sp_lay.setContentsMargins(10, 10, 10, 10)
        title = QtWidgets.QLabel("OSCILLOSCOPE  —  signal chain probe")
        title.setObjectName("sectionTitle")
        sp_lay.addWidget(title)
        sp_lay.addWidget(self.scope, 1)

        right = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        right.addWidget(self.frontend)
        right.addWidget(self.results)
        right.setStretchFactor(0, 0)
        right.setStretchFactor(1, 1)

        chain_panel = Panel("DSP SIGNAL CHAIN  —  TP4 block diagram")
        chain_panel.add(self.chain, 1)

        left = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        left.addWidget(self.editor)
        left.addWidget(chain_panel)
        left.setStretchFactor(0, 1)
        left.setStretchFactor(1, 0)
        left.setSizes([560, 330])

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(scope_panel)
        splitter.addWidget(right)
        splitter.setSizes([380, 720, 400])

        root = QtWidgets.QWidget()
        root.setObjectName("root")
        lay = QtWidgets.QHBoxLayout(root)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(splitter)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

        # --- signals ---
        self.editor.specChanged.connect(self._on_spec)
        self.frontend.feChanged.connect(self._on_fe)

        # --- timers ---
        self._scope_timer = QtCore.QTimer(self)
        self._scope_timer.timeout.connect(self._tick_scope)
        self._scope_timer.start(int(1000 / SCOPE_FPS))

        self._meas_timer = QtCore.QTimer(self)
        self._meas_timer.timeout.connect(self._tick_measurement)
        self._meas_timer.start(MEAS_INTERVAL_MS)

        self._tick_measurement()

    # --- control callbacks ---
    def _on_spec(self, spec: SignalSpec) -> None:
        self._spec = spec
        self._meas_dirty = True

    def _on_fe(self, fe: FrontEndConfig) -> None:
        self._fe = fe
        self._meas_dirty = True

    # --- live updates ---
    def _tick_scope(self) -> None:
        window = SCOPE_CYCLES / self._spec.f0
        result = pipeline.run_scope(self._spec, self._fe, window, self._t_offset)
        self.scope.update_result(result)
        self.frontend.update_fill(
            result.voltage.fill_pct, result.voltage.clipped,
            result.current.fill_pct, result.current.clipped)
        self._t_offset += SCROLL_FRACTION / self._spec.f0

    def _tick_measurement(self) -> None:
        if not self._meas_dirty:
            return
        self._meas_dirty = False
        try:
            res = pipeline.run_measurement(self._spec, self._fe, n_blocks=5)
        except Exception as exc:  # keep the UI alive on bad inputs
            self.statusBar().showMessage(f"DSP error: {exc}")
            return
        self.results.update_results(res.measured, res.reference)
        warn = ""
        if res.measured.n_blocks == 0:
            warn = "  |  no zero-crossings (raise fundamental amplitude)"
        self.statusBar().showMessage(
            f"f={res.measured.frequency:.2f} Hz   "
            f"blocks={res.measured.n_blocks}   "
            f"DPF={res.measured.dpf:.3f}{warn}")
