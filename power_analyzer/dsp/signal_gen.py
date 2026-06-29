"""Synthesize the "analog" v(t) and i(t) from a SignalSpec.

Mirrors the construction in PA.ipynb cell 0 but driven by the per-harmonic
editor: fundamental + DC + arbitrary harmonics + gaussian noise.
"""

from __future__ import annotations

import numpy as np

from core import config
from core.models import ChannelSpec, SignalSpec


def _build_channel(spec: ChannelSpec, f0: float, t: np.ndarray,
                   rng: np.random.Generator) -> np.ndarray:
    sig = np.full_like(t, spec.dc_offset)
    phase = np.deg2rad(spec.phase_deg)
    sig += spec.fundamental * np.sin(2.0 * np.pi * f0 * t + phase)
    for idx, amp in enumerate(spec.harmonic_amps):
        if amp == 0.0:
            continue
        order = idx + 2  # index 0 -> 2nd harmonic
        sig += amp * np.sin(2.0 * np.pi * order * f0 * t)
    if spec.noise_std > 0.0:
        sig += rng.normal(0.0, spec.noise_std, size=t.shape)
    return sig


def generate(spec: SignalSpec, duration: float, fs: float = config.FS_ANALOG,
             t_offset: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(t, v_analog, i_analog)`` over ``duration`` seconds.

    ``t_offset`` lets the live scope keep a continuous phase across frames so
    the trace appears to stream rather than jump.
    """
    n = int(round(duration * fs))
    t = t_offset + np.arange(n) / fs
    rng = np.random.default_rng(spec.seed)
    v = _build_channel(spec.voltage, spec.f0, t, rng)
    i = _build_channel(spec.current, spec.f0, t, rng)
    return t, v, i
