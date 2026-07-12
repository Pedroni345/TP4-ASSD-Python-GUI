"""Per-frame processing for live MCU snapshots + cross-frame averaging.

The MCU sends raw ADC codes (all DSP stays on the PC side, mirroring the
simulator pipeline): codes -> physical units -> DC removal -> per-cycle
analysis. A frame spans only ~2.5 mains cycles, so measurements use 1-cycle
blocks and the UI averages over several frames ("Promediado" block of the
TP4 diagram).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import numpy as np

from acquisition.protocol import Frame
from core import config
from core.models import Measurements
from . import power_calc


@dataclass(frozen=True)
class LiveResult:
    """Everything the live UI needs from one frame."""

    t: np.ndarray          # seconds, starting at 0
    v: np.ndarray          # volts, input-referred, DC removed
    i: np.ndarray          # amps, input-referred, DC removed
    measurements: Measurements
    v_fill_pct: float      # ADC range utilisation (peak/full-scale * 100)
    i_fill_pct: float
    v_clipped: bool
    i_clipped: bool


def codes_to_physical(codes: np.ndarray, input_range: float) -> np.ndarray:
    """Map int16 ADC codes back to input volts/amps for a fixed PGA range."""
    return codes.astype(np.float64) / config.ADC_FULL_SCALE * input_range


def _fill(codes: np.ndarray) -> tuple[float, bool]:
    peak = float(np.max(np.abs(codes.astype(np.int32))))
    pct = 100.0 * peak / config.ADC_FULL_SCALE
    clipped = peak >= config.ADC_FULL_SCALE - 1
    return pct, clipped


def process_frame(frame: Frame,
                  v_range: float = config.VOLTAGE_GAINS[config.LIVE_VOLTAGE_GAIN],
                  i_range: float = config.CURRENT_GAINS[config.LIVE_CURRENT_GAIN],
                  ) -> LiveResult:
    """Convert one raw frame to physical traces + per-frame measurements."""
    v = codes_to_physical(frame.v_codes, v_range)
    i = codes_to_physical(frame.i_codes, i_range)

    # DC removal: the 1 Hz high-pass of the long-capture path needs ~1 s to
    # settle, far longer than a 51 ms frame, so subtract the frame mean
    # instead (equivalent for a near-integer number of cycles).
    v = v - np.mean(v)
    i = i - np.mean(i)

    meas = power_calc.analyze(
        v, i, fs=config.FS_MCU,
        cycles=config.LIVE_CYCLES_PER_BLOCK,
        settle=config.LIVE_SETTLE_CROSSINGS,
    )

    t = np.arange(len(v)) / config.FS_MCU
    v_pct, v_clip = _fill(frame.v_codes)
    i_pct, i_clip = _fill(frame.i_codes)
    return LiveResult(t=t, v=v, i=i, measurements=meas,
                      v_fill_pct=v_pct, i_fill_pct=i_pct,
                      v_clipped=v_clip, i_clipped=i_clip)


def average_measurements(history: list[Measurements]) -> Measurements:
    """Average scalar fields and harmonic tuples over the last N frames.

    Frames whose analysis produced no blocks (n_blocks == 0) are skipped.
    """
    valid = [m for m in history if m.n_blocks > 0]
    if not valid:
        return Measurements()

    scalars = {}
    for f in fields(Measurements):
        if f.name in ("v_harmonics", "i_harmonics", "n_blocks"):
            continue
        scalars[f.name] = float(np.mean([getattr(m, f.name) for m in valid]))

    def avg_tuple(name: str) -> tuple:
        seqs = [getattr(m, name) for m in valid if getattr(m, name)]
        if not seqs:
            return ()
        n = min(len(s) for s in seqs)
        return tuple(np.mean([s[:n] for s in seqs], axis=0).tolist())

    return Measurements(
        **scalars,
        n_blocks=int(sum(m.n_blocks for m in valid)),
        v_harmonics=avg_tuple("v_harmonics"),
        i_harmonics=avg_tuple("i_harmonics"),
    )
