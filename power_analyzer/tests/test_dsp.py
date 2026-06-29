"""Unit + integration tests for the DSP pipeline.

Run from the package root:  ../.venv/bin/python -m pytest -q
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest
from scipy.signal import windows

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config
from core.models import ChannelSpec, FrontEndConfig, SignalSpec
from dsp import analog_frontend, ideal, pipeline, power_calc, signal_gen
from dsp.goertzel import goertzel_windowed
from dsp.zero_crossing import find_positive_crossings, make_blocks


# --------------------------------------------------------------------------
# Goertzel
# --------------------------------------------------------------------------
def test_goertzel_recovers_amplitude_and_phase():
    fs = 5000.0
    f = 50.0
    n = int(fs / f) * 10           # 10 whole cycles
    t = np.arange(n) / fs
    amp, phase = 7.0, np.deg2rad(20.0)
    x = amp * np.sin(2 * np.pi * f * t + phase)

    win = windows.hann(n)
    cg = np.mean(win)
    phasor = goertzel_windowed(x * win, fs, f, cg)

    assert phasor != 0
    assert abs(np.abs(phasor) - amp) / amp < 0.02


def test_goertzel_relative_phase_between_two_tones():
    fs = 5000.0
    f = 50.0
    n = int(fs / f) * 10
    t = np.arange(n) / fs
    v = np.sin(2 * np.pi * f * t)            # 0 deg
    i = np.sin(2 * np.pi * f * t - np.deg2rad(30))  # lags by 30 deg

    win = windows.hann(n)
    cg = np.mean(win)
    vph = goertzel_windowed(v * win, fs, f, cg)
    iph = goertzel_windowed(i * win, fs, f, cg)
    phi = np.rad2deg(np.angle(np.conjugate(vph) * iph))
    assert phi == pytest.approx(30.0, abs=0.5)


# --------------------------------------------------------------------------
# Zero crossing
# --------------------------------------------------------------------------
def test_positive_crossings_count():
    fs = 5000.0
    f = 50.0
    t = np.arange(int(fs)) / fs    # 1 second -> 50 cycles
    x = np.sin(2 * np.pi * f * t)
    times, idx = find_positive_crossings(x, fs)
    assert abs(len(times) - 50) <= 1


def test_make_blocks_frequency_estimate():
    fs = 5000.0
    f = 50.0
    t = np.arange(int(fs)) / fs
    x = np.sin(2 * np.pi * f * t)
    blocks = make_blocks(x, fs)
    assert len(blocks) >= 3
    for _s, _e, f_est in blocks:
        assert f_est == pytest.approx(50.0, abs=0.2)


# --------------------------------------------------------------------------
# Analog front-end
# --------------------------------------------------------------------------
def test_adc_quantization_step():
    bits, vref = 4, 3.0
    x = np.linspace(-vref, vref, 1000)
    q = analog_frontend.quantize(x, bits, vref)
    step = (2 * vref) / (2 ** bits)
    # spacing between unique quantized levels equals the LSB step
    diffs = np.diff(np.unique(np.round(q, 9)))
    assert np.allclose(diffs, step, atol=1e-9)


def test_frontend_clip_and_fill():
    fe = FrontEndConfig(voltage_gain="G32")  # +/- 46 V range
    t = np.arange(2000) / config.FS_ANALOG
    # 40 V peak fits in the 46 V range -> ~87% fill, no clip
    sig = 40.0 * np.sin(2 * np.pi * 50 * t)
    tr = analog_frontend.process_channel(sig, t, fe.voltage_range, fe)
    assert not tr.clipped
    assert 80.0 < tr.fill_pct < 95.0
    # 60 V peak exceeds the range -> clips
    big = 60.0 * np.sin(2 * np.pi * 50 * t)
    tr2 = analog_frontend.process_channel(big, t, fe.voltage_range, fe)
    assert tr2.clipped
    assert tr2.fill_pct > 100.0


# --------------------------------------------------------------------------
# Power calc against analytic values (clean signal, no noise)
# --------------------------------------------------------------------------
def test_power_calc_matches_analytic():
    v = ChannelSpec(fundamental=325.0, dc_offset=0.0, noise_std=0.0)
    i = ChannelSpec(fundamental=10.0, dc_offset=0.0, noise_std=0.0, phase_deg=-30.0)
    spec = SignalSpec(f0=50.0, voltage=v, current=i, seed=1)

    t, va, ia = signal_gen.generate(spec, 2.0)
    from dsp import filters
    vs = filters.anti_alias_filter(va, 2000.0, config.FS_ANALOG)[::config.DECIMATION]
    is_ = filters.anti_alias_filter(ia, 2000.0, config.FS_ANALOG)[::config.DECIMATION]
    v_dig = filters.high_pass_filter(vs, 1.0, config.FS_DIGITAL)
    i_dig = filters.high_pass_filter(is_, 1.0, config.FS_DIGITAL)

    m = power_calc.analyze(v_dig, i_dig)
    assert m.vrms == pytest.approx(325 / np.sqrt(2), rel=0.01)
    assert m.irms == pytest.approx(10 / np.sqrt(2), rel=0.01)
    assert m.dpf == pytest.approx(np.cos(np.deg2rad(30)), abs=0.01)
    assert m.phi_deg == pytest.approx(30.0, abs=0.5)
    assert m.p_fund == pytest.approx(0.5 * 325 * 10 * np.cos(np.deg2rad(30)), rel=0.02)
    assert m.q_fund > 0  # inductive load -> positive reactive power


# --------------------------------------------------------------------------
# Ideal reference
# --------------------------------------------------------------------------
def test_ideal_reference_values():
    spec = SignalSpec.default()
    r = ideal.compute(spec)
    assert r.dpf == pytest.approx(np.cos(np.deg2rad(30)), abs=1e-6)
    assert r.frequency == 50.0
    assert r.thd_v > 0
    # vrms = sqrt(sum of half-amplitude-squares)
    amps = [spec.voltage.fundamental] + [a for a in spec.voltage.harmonic_amps]
    expected = np.sqrt(sum(0.5 * a ** 2 for a in amps))
    assert r.vrms == pytest.approx(expected, rel=1e-6)


# --------------------------------------------------------------------------
# Full pipeline vs ideal (the headline acceptance test)
# --------------------------------------------------------------------------
def test_pipeline_default_matches_ideal():
    res = pipeline.run_measurement(SignalSpec.default(), FrontEndConfig(), n_blocks=8)
    m, r = res.measured, res.reference
    assert m.n_blocks >= 6
    assert m.vrms == pytest.approx(r.vrms, rel=0.01)
    assert m.irms == pytest.approx(r.irms, rel=0.02)
    assert m.frequency == pytest.approx(50.0, abs=0.05)
    assert m.dpf == pytest.approx(r.dpf, abs=0.01)
    assert m.p_fund == pytest.approx(r.p_fund, rel=0.02)
    assert m.thd_v == pytest.approx(r.thd_v, rel=0.05)


def test_pipeline_handles_silent_signal():
    """No fundamental -> no crossings -> empty measurements, no crash."""
    v = ChannelSpec(fundamental=0.0, dc_offset=0.0, noise_std=0.0)
    i = ChannelSpec(fundamental=0.0, dc_offset=0.0, noise_std=0.0)
    spec = SignalSpec(f0=50.0, voltage=v, current=i, seed=0)
    res = pipeline.run_measurement(spec, FrontEndConfig())
    assert res.measured.n_blocks == 0
