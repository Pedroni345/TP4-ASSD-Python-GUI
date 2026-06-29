"""Immutable data models shared across the DSP pipeline and the UI.

Following the project's immutability preference, these are frozen dataclasses;
mutate by building a new copy with ``dataclasses.replace``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import List

import numpy as np

from . import config


@dataclass(frozen=True)
class ChannelSpec:
    """Description of one synthetic analog channel (voltage or current)."""

    fundamental: float            # fundamental amplitude (peak)
    dc_offset: float              # DC offset added before the high-pass
    noise_std: float              # gaussian noise std-dev
    # harmonic_amps[k] is the peak amplitude of harmonic order (k + 2),
    # i.e. index 0 -> 2nd harmonic, matching the notebook convention.
    harmonic_amps: tuple = ()
    phase_deg: float = 0.0        # phase of the fundamental in degrees

    def harmonic_amp(self, order: int) -> float:
        """Peak amplitude of a given harmonic order (1 = fundamental)."""
        if order == 1:
            return self.fundamental
        idx = order - 2
        if 0 <= idx < len(self.harmonic_amps):
            return float(self.harmonic_amps[idx])
        return 0.0


@dataclass(frozen=True)
class SignalSpec:
    """Full specification of the v(t) / i(t) pair to synthesize."""

    f0: float
    voltage: ChannelSpec
    current: ChannelSpec
    seed: int | None = None       # noise seed; None = fresh noise every frame

    @staticmethod
    def default() -> "SignalSpec":
        v = ChannelSpec(
            fundamental=config.V_FUND_DEFAULT,
            dc_offset=config.V_DC_DEFAULT,
            noise_std=config.V_NOISE_DEFAULT,
            harmonic_amps=tuple(config.V_HARMONIC_AMPS_DEFAULT),
            phase_deg=0.0,
        )
        i_harm = [0.0] * (config.MAX_HARMONIC - 1)
        i_harm[1] = config.I_THIRD_DEFAULT  # index 1 -> 3rd harmonic
        i = ChannelSpec(
            fundamental=config.I_FUND_DEFAULT,
            dc_offset=config.I_DC_DEFAULT,
            noise_std=config.I_NOISE_DEFAULT,
            harmonic_amps=tuple(i_harm),
            phase_deg=-config.PHASE_LAG_DEFAULT,
        )
        return SignalSpec(f0=config.F0_DEFAULT, voltage=v, current=i)

    def with_voltage(self, **changes) -> "SignalSpec":
        return replace(self, voltage=replace(self.voltage, **changes))

    def with_current(self, **changes) -> "SignalSpec":
        return replace(self, current=replace(self.current, **changes))


@dataclass(frozen=True)
class FrontEndConfig:
    """Analog-front-end / ADC configuration set from the UI."""

    voltage_gain: str = config.DEFAULT_VOLTAGE_GAIN
    current_gain: str = config.DEFAULT_CURRENT_GAIN
    antialias_cutoff: float = config.ANTIALIAS_CUTOFF
    highpass_cutoff: float = config.HIGHPASS_CUTOFF
    adc_bits: int = config.ADC_BITS

    @property
    def voltage_range(self) -> float:
        return config.VOLTAGE_GAINS[self.voltage_gain]

    @property
    def current_range(self) -> float:
        return config.CURRENT_GAINS[self.current_gain]


@dataclass(frozen=True)
class StageTraces:
    """Time-domain traces tapped at each point of the chain (one channel).

    Arrays at the analog rate share ``t_analog``; digital-rate arrays share
    ``t_digital``. Units are physical (V or A), referred back to the input.
    """

    t_analog: np.ndarray
    raw: np.ndarray                # raw synthetic analog input
    antialiased: np.ndarray        # after the anti-alias low-pass
    t_digital: np.ndarray
    adc: np.ndarray                # after decimation + quantization (input-referred)
    highpass: np.ndarray           # after the digital DC-removal high-pass
    fill_pct: float                # ADC range utilisation (peak/VREF * 100)
    clipped: bool                  # True if the signal exceeded +/- VREF


@dataclass(frozen=True)
class Measurements:
    """Results of the DSP pipeline (averaged over N blocks)."""

    vrms: float = 0.0
    irms: float = 0.0
    frequency: float = 0.0
    p_total: float = 0.0
    q_total: float = 0.0
    s_total: float = 0.0
    tpf: float = 0.0
    p_fund: float = 0.0
    q_fund: float = 0.0
    s_fund: float = 0.0
    phi_deg: float = 0.0
    dpf: float = 0.0
    thd_v: float = 0.0
    thd_i: float = 0.0
    n_blocks: int = 0
    v_harmonics: tuple = ()        # normalized |V_k| (k = 1..)
    i_harmonics: tuple = ()        # normalized |I_k|


# IdealReference uses the same field layout as Measurements so the results
# panel can diff them field-by-field.
IdealReference = Measurements
