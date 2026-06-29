"""Butterworth filter helpers, ported from PA.ipynb cell 0.

The cutoff frequencies are parameters here so the UI can sweep them live.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, lfilter

from core import config


def anti_alias_filter(signal: np.ndarray, cutoff_hz: float, fs: float,
                      order: int = config.ANTIALIAS_ORDER) -> np.ndarray:
    """Causal low-pass, emulating the analog anti-alias filter before the ADC."""
    nyq = 0.5 * fs
    wn = min(max(cutoff_hz / nyq, 1e-6), 0.999)
    b, a = butter(order, wn, btype="low")
    return lfilter(b, a, signal)


def dc_blocker(signal: np.ndarray, cutoff_hz: float, fs: float) -> np.ndarray:
    """First-order IIR DC remover -- the real-time / MCU high-pass.

    This is the floating-point twin of the TI MSP430 e-meter ``dc_filter``
    (``dc_filter16.c``). A leaky integrator continuously *estimates* the DC
    level and that estimate is subtracted from every incoming sample. TI's
    fixed-point inner loop is::

        *p += (((int32_t) x << 16) - *p) >> 14;   // dc += alpha*(x - dc)
        x  -= (*p >> 16);                          // out = x - dc

    i.e. a one-pole low-pass DC estimate (there ``alpha = 2**-14``) subtracted
    from the signal. Subtracting a one-pole low-pass IS the canonical DC-blocker
    high-pass::

        H(z) = (1 - z^-1) / (1 - r z^-1),   pole r = 1 - alpha.

    We derive the pole from the requested ``cutoff_hz`` (instead of locking it
    to a power-of-two shift as TI does) so the UI cut-off control stays exact::

        r = exp(-2*pi*fc/fs),   so 1 - r ~= 2*pi*fc/fs = alpha.

    Numerator zero at z=1 kills DC; passband gain is ~1 (2/(1+r) at Nyquist),
    so RMS is preserved. Being first-order and unconditionally stable, it has a
    clean exponential settling (tau = 1/(2*pi*fc)) and no ringing -- exactly the
    behaviour an MCU implementation has, and what the live scope shows.
    """
    r = float(np.exp(-2.0 * np.pi * cutoff_hz / fs))
    return lfilter([1.0, -1.0], [1.0, -r], signal)


def high_pass_filter(signal: np.ndarray, cutoff_hz: float, fs: float,
                     order: int = config.HIGHPASS_ORDER,
                     causal: bool = False) -> np.ndarray:
    """Digital high-pass that removes DC / input offsets after the ADC.

    Two regimes, matching the two views of the instrument:

    * ``causal=True`` -> :func:`dc_blocker`, the first-order leaky-integrator
      that a real microcontroller actually runs sample-by-sample (TI style).
      Used by the live scope, which supplies enough pre-roll for the DC
      estimate to settle.
    * ``causal=False`` -> zero-phase Butterworth (``filtfilt``), as in the
      reference notebook. No transient and no phase shift, so it is used for
      the offline measurement column that we hold up as the DSP reference.
    """
    if causal:
        return dc_blocker(signal, cutoff_hz, fs)
    nyq = 0.5 * fs
    wn = min(max(cutoff_hz / nyq, 1e-6), 0.999)
    b, a = butter(order, wn, btype="high")
    padlen = 3 * (max(len(a), len(b)) - 1)
    if len(signal) <= padlen:
        return signal - np.mean(signal)
    return filtfilt(b, a, signal)
