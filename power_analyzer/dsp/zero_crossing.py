"""Interpolated positive zero-crossing detection and 10-cycle block slicing.

Ported from PA.ipynb cell 0 (``find_all_crossings`` + the block loop). The
voltage channel is normally used to find crossings (less distortion than the
current).
"""

from __future__ import annotations

import numpy as np

from core import config


def find_positive_crossings(signal: np.ndarray, fs: float):
    """Return ``(times, indices)`` of positive-going zero crossings.

    Times are linearly interpolated between samples for sub-sample precision;
    indices snap to the first sample at/after the crossing for slicing.
    """
    times: list[float] = []
    indices: list[int] = []
    for i in range(1, len(signal)):
        if signal[i - 1] <= 0 and signal[i] > 0:
            y1 = abs(signal[i - 1])
            y2 = signal[i]
            frac = y1 / (y1 + y2) if (y1 + y2) else 0.0
            t_cross = ((i - 1) / fs) + frac * (1.0 / fs)
            times.append(t_cross)
            indices.append(i)
    return times, indices


def make_blocks(signal_for_crossings: np.ndarray, fs: float,
                cycles: int = config.CYCLES_PER_BLOCK,
                settle: int = config.SETTLE_CROSSINGS):
    """Yield block descriptors of exactly ``cycles`` whole cycles.

    Each descriptor is ``(start_idx, end_idx, f_est)`` where ``f_est`` is the
    precise fundamental frequency measured from the crossing interval.
    """
    times, indices = find_positive_crossings(signal_for_crossings, fs)
    times = times[settle:]
    indices = indices[settle:]
    if len(times) <= cycles:
        return []

    total_blocks = (len(times) - 1) // cycles
    blocks = []
    for j in range(total_blocks):
        t_start = times[j * cycles]
        t_end = times[j * cycles + cycles]
        start_idx = indices[j * cycles]
        end_idx = indices[j * cycles + cycles]
        if end_idx <= start_idx:
            continue
        f_est = cycles / (t_end - t_start)
        blocks.append((start_idx, end_idx, f_est))
    return blocks
