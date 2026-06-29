"""Analog front-end model: PGA gain -> anti-alias -> ADC -> high-pass.

Everything is kept *input-referred* (volts or amps at the J1/J2 terminals) so
the scope can overlay every stage on the same axis. The hardware reality (the
signal living in +/- VREF inside the ADC) shows up as the quantization step
size and the clipping behaviour.
"""

from __future__ import annotations

import numpy as np

from core import config
from core.models import FrontEndConfig, StageTraces
from .filters import anti_alias_filter, high_pass_filter


def quantize(adc_volts: np.ndarray, bits: int, vref: float) -> np.ndarray:
    """Clip to +/- vref and round to the nearest of 2**bits levels."""
    clipped = np.clip(adc_volts, -vref, vref)
    levels = 2 ** bits
    step = (2.0 * vref) / levels
    # map [-vref, vref) onto integer codes, then back to volts (mid-tread)
    codes = np.round(clipped / step)
    codes = np.clip(codes, -(levels // 2), levels // 2 - 1)
    return codes * step


def process_channel(raw_analog: np.ndarray, t_analog: np.ndarray,
                    range_peak: float, fe: FrontEndConfig,
                    fs_analog: float = config.FS_ANALOG,
                    fs_digital: float = config.FS_DIGITAL,
                    hp_causal: bool = False) -> StageTraces:
    """Run one channel through the front-end and return all stage traces.

    ``range_peak`` is the input peak (V or A) that the selected PGA gain maps to
    full ADC scale (+/- VREF).
    """
    vref = config.ADC_VREF
    # PGA: input volts/amps -> ADC volts.
    to_adc = vref / range_peak
    from_adc = range_peak / vref  # input-referred conversion back

    # 1. Anti-alias low-pass on the high-rate signal.
    antialiased = anti_alias_filter(raw_analog, fe.antialias_cutoff, fs_analog)

    # 2. Decimate to the ADC sample rate.
    dec = int(round(fs_analog / fs_digital))
    sampled = antialiased[::dec]
    t_digital = t_analog[::dec]

    # 3. ADC: scale into +/- VREF, quantize, then refer the result back to the
    #    input so it overlays the analog traces.
    adc_volts = sampled * to_adc
    quantized = quantize(adc_volts, fe.adc_bits, vref)
    adc_input_referred = quantized * from_adc

    # 4. Digital high-pass to strip the DC / offset.
    highpass = high_pass_filter(adc_input_referred, fe.highpass_cutoff,
                                fs_digital, causal=hp_causal)

    # Range utilisation / clip detection (based on what reaches the ADC).
    peak = float(np.max(np.abs(sampled))) if sampled.size else 0.0
    fill_pct = 100.0 * peak / range_peak if range_peak else 0.0
    clipped = peak > range_peak

    return StageTraces(
        t_analog=t_analog,
        raw=raw_analog,
        antialiased=antialiased,
        t_digital=t_digital,
        adc=adc_input_referred,
        highpass=highpass,
        fill_pct=fill_pct,
        clipped=clipped,
    )
