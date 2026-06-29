"""Full per-harmonic input-signal editor for v(t) and i(t)."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from core import config
from core.models import ChannelSpec, SignalSpec
from . import theme
from .widgets import Panel


def _spin(maximum: float, value: float, step: float, suffix: str = "",
          minimum: float = 0.0, decimals: int = 1) -> QtWidgets.QDoubleSpinBox:
    s = QtWidgets.QDoubleSpinBox()
    s.setRange(minimum, maximum)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    s.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
    return s


class HarmonicEditor(Panel):
    """Edits the SignalSpec; emits ``specChanged`` on every change."""

    specChanged = QtCore.pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__("INPUT SIGNAL GENERATOR", parent)
        self._loading = True
        spec = SignalSpec.default()

        # --- global + per-channel scalar controls ---
        form = QtWidgets.QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(4)
        form.addWidget(self._hdr(""), 0, 0)
        form.addWidget(self._hdr("VOLTAGE", theme.V_COLOR), 0, 1)
        form.addWidget(self._hdr("CURRENT", theme.I_COLOR), 0, 2)

        self.f0 = _spin(400.0, spec.f0, 1.0, " Hz", minimum=10.0)
        self.v_fund = _spin(2000.0, spec.voltage.fundamental, 5.0, " V")
        self.i_fund = _spin(50.0, spec.current.fundamental, 0.5, " A")
        self.v_dc = _spin(500.0, spec.voltage.dc_offset, 1.0, " V", minimum=-500.0)
        self.i_dc = _spin(50.0, spec.current.dc_offset, 0.5, " A", minimum=-50.0)
        self.v_phase = _spin(180.0, spec.voltage.phase_deg, 5.0, " deg", minimum=-180.0)
        self.i_phase = _spin(180.0, spec.current.phase_deg, 5.0, " deg", minimum=-180.0)
        self.v_noise = _spin(100.0, spec.voltage.noise_std, 1.0, " V")
        self.i_noise = _spin(20.0, spec.current.noise_std, 0.1, " A", decimals=2)

        rows = [
            ("Fundamental", self.v_fund, self.i_fund),
            ("DC offset", self.v_dc, self.i_dc),
            ("Phase", self.v_phase, self.i_phase),
            ("Noise (sigma)", self.v_noise, self.i_noise),
        ]
        form.addWidget(self._lbl("Frequency"), 1, 0)
        form.addWidget(self.f0, 1, 1)
        for r, (name, wv, wi) in enumerate(rows, start=2):
            form.addWidget(self._lbl(name), r, 0)
            form.addWidget(wv, r, 1)
            form.addWidget(wi, r, 2)
        self.add_layout(form)

        self.add(self._sep("HARMONICS  (amplitude per order)"))

        # --- per-harmonic table ---
        orders = list(range(2, config.MAX_HARMONIC + 1))
        self.table = QtWidgets.QTableWidget(len(orders), 3)
        self.table.setHorizontalHeaderLabels(["Order", "V amp [V]", "I amp [A]"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._v_harm: list[QtWidgets.QDoubleSpinBox] = []
        self._i_harm: list[QtWidgets.QDoubleSpinBox] = []
        for row, order in enumerate(orders):
            item = QtWidgets.QTableWidgetItem(f"{order}  ({order * 50} Hz)")
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, item)
            sv = _spin(500.0, spec.voltage.harmonic_amp(order), 1.0)
            si = _spin(20.0, spec.current.harmonic_amp(order), 0.1, decimals=2)
            self._v_harm.append(sv)
            self._i_harm.append(si)
            self.table.setCellWidget(row, 1, sv)
            self.table.setCellWidget(row, 2, si)
        self.add(self.table, 1)

        # wire up
        for w in [self.f0, self.v_fund, self.i_fund, self.v_dc, self.i_dc,
                  self.v_phase, self.i_phase, self.v_noise, self.i_noise,
                  *self._v_harm, *self._i_harm]:
            w.valueChanged.connect(self._emit)

        self._loading = False

    # -- helpers --
    @staticmethod
    def _lbl(text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("metricLabel")
        return lbl

    @staticmethod
    def _hdr(text: str, color: str = theme.TEXT_DIM) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(f"color:{color}; font-weight:bold;")
        return lbl

    def _sep(self, text: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def build_spec(self) -> SignalSpec:
        v = ChannelSpec(
            fundamental=self.v_fund.value(),
            dc_offset=self.v_dc.value(),
            noise_std=self.v_noise.value(),
            harmonic_amps=tuple(s.value() for s in self._v_harm),
            phase_deg=self.v_phase.value(),
        )
        i = ChannelSpec(
            fundamental=self.i_fund.value(),
            dc_offset=self.i_dc.value(),
            noise_std=self.i_noise.value(),
            harmonic_amps=tuple(s.value() for s in self._i_harm),
            phase_deg=self.i_phase.value(),
        )
        return SignalSpec(f0=self.f0.value(), voltage=v, current=i)

    def _emit(self) -> None:
        if not self._loading:
            self.specChanged.emit(self.build_spec())
