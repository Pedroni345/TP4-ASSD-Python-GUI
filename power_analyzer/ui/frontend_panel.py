"""Analog-front-end controls: PGA gain, ADC fill, filter cutoffs."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from core import config
from core.models import FrontEndConfig
from . import theme
from .widgets import FillBar, Panel


class FrontEndPanel(Panel):
    """Edits the FrontEndConfig; emits ``feChanged`` on every change."""

    feChanged = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__("ANALOG FRONT-END  /  ADC", parent)
        self._loading = True
        fe = FrontEndConfig()

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        # --- PGA gain selectors ---
        grid.addWidget(self._sec("DIFFERENTIAL AMP  (PGA281A)"), 0, 0, 1, 2)

        self.v_gain = QtWidgets.QComboBox()
        for code, peak in config.VOLTAGE_GAINS.items():
            self.v_gain.addItem(f"{code}   +/-{peak:.0f} V", code)
        self.v_gain.setCurrentIndex(list(config.VOLTAGE_GAINS).index(fe.voltage_gain))

        self.i_gain = QtWidgets.QComboBox()
        for code, peak in config.CURRENT_GAINS.items():
            self.i_gain.addItem(f"{code}   +/-{peak:.2f} A", code)
        self.i_gain.setCurrentIndex(list(config.CURRENT_GAINS).index(fe.current_gain))

        grid.addWidget(self._lbl("V gain", theme.V_COLOR), 1, 0)
        grid.addWidget(self.v_gain, 1, 1)
        self.v_fill = FillBar()
        grid.addWidget(self.v_fill, 2, 0, 1, 2)

        grid.addWidget(self._lbl("I gain", theme.I_COLOR), 3, 0)
        grid.addWidget(self.i_gain, 3, 1)
        self.i_fill = FillBar()
        grid.addWidget(self.i_fill, 4, 0, 1, 2)

        # --- ADC ---
        grid.addWidget(self._sec("ADC  (MCP3313LD-05)"), 5, 0, 1, 2)
        self.bits = QtWidgets.QComboBox()
        for b in (8, 10, 12, 14, 16):
            self.bits.addItem(f"{b} bit", b)
        self.bits.setCurrentIndex([8, 10, 12, 14, 16].index(fe.adc_bits))
        grid.addWidget(self._lbl("Resolution"), 6, 0)
        grid.addWidget(self.bits, 6, 1)
        grid.addWidget(self._lbl("Sample rate"), 7, 0)
        grid.addWidget(self._dim(f"{config.FS_DIGITAL/1000:.0f} kHz  (Vref +/-{config.ADC_VREF:.0f} V)"), 7, 1)

        # --- Filters ---
        grid.addWidget(self._sec("FILTERS  (adjustable cut-off)"), 8, 0, 1, 2)
        self.antialias = QtWidgets.QDoubleSpinBox()
        self.antialias.setRange(50.0, config.FS_DIGITAL / 2.0)
        self.antialias.setSingleStep(50.0)
        self.antialias.setSuffix(" Hz")
        self.antialias.setDecimals(0)
        self.antialias.setValue(fe.antialias_cutoff)
        grid.addWidget(self._lbl("Anti-alias LP"), 9, 0)
        grid.addWidget(self.antialias, 9, 1)

        self.highpass = QtWidgets.QDoubleSpinBox()
        self.highpass.setRange(0.1, 200.0)
        self.highpass.setSingleStep(0.5)
        self.highpass.setSuffix(" Hz")
        self.highpass.setDecimals(1)
        self.highpass.setValue(fe.highpass_cutoff)
        grid.addWidget(self._lbl("DC-removal HP"), 10, 0)
        grid.addWidget(self.highpass, 10, 1)

        self.add_layout(grid)
        self.add(self._isolation_badge())
        self.content.addStretch(1)

        for w in (self.v_gain, self.i_gain, self.bits):
            w.currentIndexChanged.connect(self._emit)
        for w in (self.antialias, self.highpass):
            w.valueChanged.connect(self._emit)

        self._loading = False

    # -- helpers --
    @staticmethod
    def _lbl(text: str, color: str = theme.TEXT_DIM) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(f"color:{color};")
        return lbl

    @staticmethod
    def _dim(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("dimText")
        return lbl

    @staticmethod
    def _sec(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    @staticmethod
    def _isolation_badge() -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel("- - - |  GALVANIC ISOLATION (ISO7731)  | - - -")
        lbl.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color:{theme.AMBER}; border:1px dashed {theme.AMBER};"
            f"border-radius:5px; padding:4px; margin-top:6px;")
        return lbl

    def build_config(self) -> FrontEndConfig:
        return FrontEndConfig(
            voltage_gain=self.v_gain.currentData(),
            current_gain=self.i_gain.currentData(),
            antialias_cutoff=self.antialias.value(),
            highpass_cutoff=self.highpass.value(),
            adc_bits=self.bits.currentData(),
        )

    def update_fill(self, v_fill_pct: float, v_clip: bool,
                    i_fill_pct: float, i_clip: bool) -> None:
        self.v_fill.set_value(v_fill_pct, v_clip)
        self.i_fill.set_value(i_fill_pct, i_clip)

    def _emit(self) -> None:
        if not self._loading:
            self.feChanged.emit(self.build_config())
