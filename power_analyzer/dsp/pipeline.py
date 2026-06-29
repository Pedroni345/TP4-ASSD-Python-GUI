"""End-to-end orchestration: SignalSpec + FrontEndConfig -> traces + results.

Two entry points keep the live UI smooth:
  * ``run_scope``      -- cheap, returns per-stage traces for a short window.
  * ``run_measurement`` -- full DSP over enough cycles for stable numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core import config
from core.models import FrontEndConfig, Measurements, SignalSpec, StageTraces
from . import analog_frontend, ideal, power_calc, signal_gen


@dataclass(frozen=True)
class ScopeResult:
    voltage: StageTraces
    current: StageTraces


# Scope buffers use a lighter oversample than the measurement path (still well
# above the 2 kHz anti-alias) so each live frame stays cheap.
SCOPE_FS_ANALOG = 25_000.0
# Pre-roll long enough for the 1 Hz digital high-pass to settle (tau ~ 0.16 s).
SCOPE_PREROLL = 1.2


def _trim(tr: StageTraces, t0: float) -> StageTraces:
    """Keep only samples at/after ``t0`` and rebase time to start at zero."""
    a = tr.t_analog >= t0
    d = tr.t_digital >= t0
    return StageTraces(
        t_analog=tr.t_analog[a] - t0,
        raw=tr.raw[a],
        antialiased=tr.antialiased[a],
        t_digital=tr.t_digital[d] - t0,
        adc=tr.adc[d],
        highpass=tr.highpass[d],
        fill_pct=tr.fill_pct,
        clipped=tr.clipped,
    )


@dataclass(frozen=True)
class MeasurementResult:
    measured: Measurements
    reference: Measurements  # analytic ideal


def run_scope(spec: SignalSpec, fe: FrontEndConfig, duration: float,
              t_offset: float = 0.0) -> ScopeResult:
    """Tap every stage of both channels over a steady display window.

    A pre-roll is generated before the visible ``duration`` so the causal
    anti-alias filter and the slow digital high-pass reach steady state; the
    result is then trimmed to the window and time-rebased to zero.
    """
    gen_start = t_offset - SCOPE_PREROLL
    gen_dur = SCOPE_PREROLL + duration
    t, v, i = signal_gen.generate(spec, gen_dur, fs=SCOPE_FS_ANALOG, t_offset=gen_start)

    v_tr = analog_frontend.process_channel(v, t, fe.voltage_range, fe,
                                           fs_analog=SCOPE_FS_ANALOG, hp_causal=True)
    i_tr = analog_frontend.process_channel(i, t, fe.current_range, fe,
                                           fs_analog=SCOPE_FS_ANALOG, hp_causal=True)
    return ScopeResult(voltage=_trim(v_tr, t_offset), current=_trim(i_tr, t_offset))


def run_measurement(spec: SignalSpec, fe: FrontEndConfig,
                    n_blocks: int = 6) -> MeasurementResult:
    """Run the full pipeline over enough cycles for ``n_blocks`` 10-cycle blocks."""
    # Need cycles for the blocks + settling crossings, with margin.
    cycles_needed = (n_blocks + 1) * config.CYCLES_PER_BLOCK + config.SETTLE_CROSSINGS + 4
    duration = cycles_needed / spec.f0
    t, v, i = signal_gen.generate(spec, duration)

    v_tr = analog_frontend.process_channel(v, t, fe.voltage_range, fe)
    i_tr = analog_frontend.process_channel(i, t, fe.current_range, fe)

    measured = power_calc.analyze(v_tr.highpass, i_tr.highpass, config.FS_DIGITAL)
    reference = ideal.compute(spec)
    return MeasurementResult(measured=measured, reference=reference)
