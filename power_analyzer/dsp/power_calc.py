"""Per-block power analysis and N-block averaging.

Implements both processing paths from the PDF block diagram:
  * Calculo Temporal  -> Vrms, Irms, P_total, S, Q, TPF
  * Algoritmo Goertzel -> V_fund, I_fund, P/Q/S_fund, phi, DPF, harmonics, THD
"""

from __future__ import annotations

import numpy as np
from scipy.signal import windows

from core import config
from core.models import Measurements
from .goertzel import goertzel_windowed
from .zero_crossing import make_blocks


def analyze(v_dig: np.ndarray, i_dig: np.ndarray, fs: float = config.FS_DIGITAL,
            max_harmonic: int = config.MAX_HARMONIC) -> Measurements:
    """Run the full per-block analysis on the digital signals."""
    blocks = make_blocks(v_dig, fs)
    if not blocks:
        return Measurements()

    vrms_b, irms_b, p_tot_b = [], [], []
    p_fund_b, q_fund_b, s_fund_b, phi_b, freq_b = [], [], [], [], []
    v_harm = [[] for _ in range(max_harmonic)]   # index 0 -> fundamental
    i_harm = [[] for _ in range(max_harmonic)]

    for start, end, f_est in blocks:
        v_block = v_dig[start:end]
        i_block = i_dig[start:end]
        if len(v_block) < 4:
            continue
        freq_b.append(f_est)

        # --- Temporal path (raw integer-cycle block) ---
        vrms_b.append(np.sqrt(np.mean(v_block ** 2)))
        irms_b.append(np.sqrt(np.mean(i_block ** 2)))
        p_tot_b.append(np.mean(v_block * i_block))

        # --- Goertzel path (Hann-windowed) ---
        win = windows.hann(len(v_block))
        cg = np.mean(win)
        vw = v_block * win
        iw = i_block * win

        v_fund = goertzel_windowed(vw, fs, f_est, cg)
        i_fund = goertzel_windowed(iw, fs, f_est, cg)
        # conj(V)*I gives the conventional sign: phi = angle by which V leads I,
        # so an inductive (lagging) current yields positive reactive power.
        cross = np.conjugate(v_fund) * i_fund
        p_fund_b.append(0.5 * np.real(cross))
        q_fund_b.append(0.5 * np.imag(cross))
        s_fund_b.append(0.5 * np.abs(v_fund) * np.abs(i_fund))
        phi_b.append(np.angle(cross))

        v_harm[0].append(np.abs(v_fund))
        i_harm[0].append(np.abs(i_fund))
        for h in range(1, max_harmonic):
            order = h + 1
            v_harm[h].append(np.abs(goertzel_windowed(vw, fs, f_est * order, cg)))
            i_harm[h].append(np.abs(goertzel_windowed(iw, fs, f_est * order, cg)))

    vrms = float(np.mean(vrms_b))
    irms = float(np.mean(irms_b))
    p_total = float(np.mean(p_tot_b))
    s_total = vrms * irms
    q_total = float(np.sqrt(max(s_total ** 2 - p_total ** 2, 0.0)))
    tpf = p_total / s_total if s_total else 0.0

    p_fund = float(np.mean(p_fund_b))
    q_fund = float(np.mean(q_fund_b))
    s_fund = float(np.mean(s_fund_b))
    phi = float(np.mean(phi_b))
    dpf = p_fund / s_fund if s_fund else 0.0

    v_mag = np.array([np.mean(b) for b in v_harm])
    i_mag = np.array([np.mean(b) for b in i_harm])
    thd_v = 100.0 * np.sqrt(np.sum(v_mag[1:] ** 2)) / v_mag[0] if v_mag[0] else 0.0
    thd_i = 100.0 * np.sqrt(np.sum(i_mag[1:] ** 2)) / i_mag[0] if i_mag[0] else 0.0

    v_norm = tuple((v_mag / v_mag[0]).tolist()) if v_mag[0] else ()
    i_norm = tuple((i_mag / i_mag[0]).tolist()) if i_mag[0] else ()

    return Measurements(
        vrms=vrms, irms=irms, frequency=float(np.mean(freq_b)),
        p_total=p_total, q_total=q_total, s_total=s_total, tpf=tpf,
        p_fund=p_fund, q_fund=q_fund, s_fund=s_fund,
        phi_deg=np.rad2deg(phi), dpf=dpf,
        thd_v=float(thd_v), thd_i=float(thd_i),
        n_blocks=len(freq_b), v_harmonics=v_norm, i_harmonics=i_norm,
    )
