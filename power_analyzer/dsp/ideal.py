"""Analytic ("ideal") reference values computed directly from the SignalSpec.

No noise, no filtering, no quantization -- the ground truth the DSP pipeline is
trying to recover. Used for the side-by-side comparison in the results panel.
"""

from __future__ import annotations

import numpy as np

from core import config
from core.models import ChannelSpec, IdealReference, SignalSpec


def _orders_and_amps(ch: ChannelSpec, max_harmonic: int):
    """Return dict {order: (peak_amp, phase_rad)} for non-zero AC components."""
    out: dict[int, tuple[float, float]] = {}
    if ch.fundamental:
        out[1] = (ch.fundamental, np.deg2rad(ch.phase_deg))
    for order in range(2, max_harmonic + 1):
        amp = ch.harmonic_amp(order)
        if amp:
            out[order] = (amp, 0.0)  # harmonics generated at zero phase
    return out


def compute(spec: SignalSpec, max_harmonic: int = config.MAX_HARMONIC) -> IdealReference:
    v = _orders_and_amps(spec.voltage, max_harmonic)
    i = _orders_and_amps(spec.current, max_harmonic)

    # RMS over all AC components (DC removed by the high-pass).
    vrms = float(np.sqrt(sum(0.5 * a ** 2 for a, _ in v.values())))
    irms = float(np.sqrt(sum(0.5 * a ** 2 for a, _ in i.values())))

    # Total real power: only shared frequencies contribute on average.
    p_total = 0.0
    for order, (va, vp) in v.items():
        if order in i:
            ia, ip = i[order]
            p_total += 0.5 * va * ia * np.cos(vp - ip)

    s_total = vrms * irms
    q_total = float(np.sqrt(max(s_total ** 2 - p_total ** 2, 0.0)))
    tpf = p_total / s_total if s_total else 0.0

    # Fundamental.
    v1, vp1 = v.get(1, (0.0, 0.0))
    i1, ip1 = i.get(1, (0.0, 0.0))
    phi = vp1 - ip1
    p_fund = 0.5 * v1 * i1 * np.cos(phi)
    q_fund = 0.5 * v1 * i1 * np.sin(phi)
    s_fund = 0.5 * v1 * i1
    dpf = np.cos(phi) if (v1 and i1) else 0.0

    def thd(comp: dict[int, tuple[float, float]]) -> float:
        f = comp.get(1, (0.0, 0.0))[0]
        if not f:
            return 0.0
        rest = sum(a ** 2 for o, (a, _) in comp.items() if o != 1)
        return 100.0 * np.sqrt(rest) / f

    def norm(comp: dict[int, tuple[float, float]]) -> tuple:
        f = comp.get(1, (0.0, 0.0))[0]
        if not f:
            return ()
        return tuple(comp.get(o, (0.0, 0.0))[0] / f for o in range(1, max_harmonic + 1))

    return IdealReference(
        vrms=vrms, irms=irms, frequency=spec.f0,
        p_total=p_total, q_total=q_total, s_total=s_total, tpf=tpf,
        p_fund=p_fund, q_fund=q_fund, s_fund=s_fund,
        phi_deg=float(np.rad2deg(phi)), dpf=float(dpf),
        thd_v=thd(v), thd_i=thd(i),
        n_blocks=0, v_harmonics=norm(v), i_harmonics=norm(i),
    )
