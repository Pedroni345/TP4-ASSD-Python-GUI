"""Windowed Goertzel single-bin DFT, ported verbatim from PA.ipynb cell 0.

Returns the complex phasor at ``target_freq`` scaled so that ``abs`` gives the
peak amplitude of that tone (accounting for the window's coherent gain).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter


def goertzel_windowed(signal: np.ndarray, fs: float, target_freq: float,
                      coherent_gain: float) -> complex:
    """Single-bin phasor via the Goertzel recurrence.

    The recurrence ``s[n] = x[n] + coeff*s[n-1] - s[n-2]`` is a second-order
    IIR, so it is evaluated with ``lfilter`` (C speed) instead of a Python loop;
    the result is identical to the textbook loop in PA.ipynb.
    """
    n = len(signal)
    if n < 2:
        return 0j
    omega = 2.0 * np.pi * target_freq / fs
    coeff = 2.0 * np.cos(omega)

    s = lfilter([1.0], [1.0, -coeff, 1.0], signal)
    s_prev1 = s[-1]
    s_prev2 = s[-2]

    real_part = s_prev1 - s_prev2 * np.cos(omega)
    imag_part = -s_prev2 * np.sin(omega)
    return complex(real_part, imag_part) * (2.0 / (n * coherent_gain))
