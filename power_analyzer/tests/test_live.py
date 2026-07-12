"""Tests for the live-acquisition path: protocol parsing + per-frame DSP.

Run from the package root:  ../.venv/bin/python -m pytest -q
"""

from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acquisition.protocol import FRAME_BYTES, Frame, FrameParser, parse_payload
from core import config
from dsp import live


def _frame_bytes(v_codes: np.ndarray, i_codes: np.ndarray) -> bytes:
    return (config.FRAME_HEADER
            + v_codes.astype("<i2").tobytes()
            + i_codes.astype("<i2").tobytes())


def _codes(seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    v = rng.integers(-32768, 32767, config.FRAME_SAMPLES, dtype=np.int16)
    i = rng.integers(-32768, 32767, config.FRAME_SAMPLES, dtype=np.int16)
    return v, i


# --------------------------------------------------------------------------
# Protocol
# --------------------------------------------------------------------------
def test_parse_payload_roundtrip_signed():
    v, i = _codes(1)
    frame = parse_payload(_frame_bytes(v, i)[len(config.FRAME_HEADER):])
    np.testing.assert_array_equal(frame.v_codes, v)
    np.testing.assert_array_equal(frame.i_codes, i)


def test_parser_syncs_past_garbage_and_split_chunks():
    v, i = _codes(2)
    stream = b"\x13\x37garbage" + _frame_bytes(v, i)
    parser = FrameParser()
    frames: list[Frame] = []
    # Feed in awkward chunk sizes to exercise resync + partial frames.
    for k in range(0, len(stream), 97):
        frames += parser.feed(stream[k:k + 97])
    assert len(frames) == 1
    np.testing.assert_array_equal(frames[0].v_codes, v)
    np.testing.assert_array_equal(frames[0].i_codes, i)


def test_parser_handles_back_to_back_frames():
    v1, i1 = _codes(3)
    v2, i2 = _codes(4)
    parser = FrameParser()
    frames = parser.feed(_frame_bytes(v1, i1) + _frame_bytes(v2, i2))
    assert len(frames) == 2
    np.testing.assert_array_equal(frames[1].v_codes, v2)
    assert FRAME_BYTES == 4 + 4 * config.FRAME_SAMPLES


# --------------------------------------------------------------------------
# Live DSP
# --------------------------------------------------------------------------
def test_codes_to_physical_scaling():
    codes = np.array([0, 16384, -32768], dtype=np.int16)
    out = live.codes_to_physical(codes, 368.0)
    np.testing.assert_allclose(out, [0.0, 184.0, -368.0])


def test_process_frame_measures_synthetic_signal():
    import dataclasses

    from acquisition.sim_source import default_live_spec, synth_frame

    spec = dataclasses.replace(default_live_spec(), seed=42)
    v_range = config.VOLTAGE_GAINS[config.LIVE_VOLTAGE_GAIN]
    i_range = config.CURRENT_GAINS[config.LIVE_CURRENT_GAIN]
    frame = synth_frame(spec, t_offset=0.0, v_range=v_range, i_range=i_range)

    result = live.process_frame(frame, v_range, i_range)
    m = result.measurements
    assert m.n_blocks >= 1                       # 1-cycle blocks fit the frame
    assert 49.0 < m.frequency < 51.0
    assert 220.0 < m.vrms < 245.0                # ~233 V with harmonics
    assert 1.5 < m.irms < 2.1                    # ~1.8 A (2.5 A fund + 3rd)
    assert 20.0 < m.phi_deg < 40.0               # 30 deg lag configured
    assert len(result.t) == config.FRAME_SAMPLES


def test_average_measurements_skips_empty_frames():
    from core.models import Measurements

    good = Measurements(vrms=100.0, irms=2.0, n_blocks=2,
                        v_harmonics=(1.0, 0.1), i_harmonics=(1.0, 0.2))
    empty = Measurements()  # n_blocks == 0, must be ignored
    other = Measurements(vrms=200.0, irms=4.0, n_blocks=1,
                         v_harmonics=(1.0, 0.3), i_harmonics=(1.0, 0.4))

    avg = live.average_measurements([good, empty, other])
    assert avg.vrms == 150.0
    assert avg.irms == 3.0
    assert avg.n_blocks == 3
    np.testing.assert_allclose(avg.v_harmonics, (1.0, 0.2))

    assert live.average_measurements([empty]) == Measurements()
