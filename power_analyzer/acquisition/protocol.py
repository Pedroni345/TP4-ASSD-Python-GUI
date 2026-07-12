"""Pure parsing of the STM32 snapshot stream (no I/O, fully testable).

Wire format, produced by ``main.c``'s transmit loop::

    AA 55 AA 55 | V[0..511] uint16 LE | I[0..511] uint16 LE

The ADC (MCP3313, differential, +/-VREF) outputs 16-bit two's-complement
codes; the SPI peripheral assembles each word, so the little-endian payload
is simply reinterpreted as ``int16``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core import config

CHANNEL_BYTES = config.FRAME_SAMPLES * 2
PAYLOAD_BYTES = 2 * CHANNEL_BYTES
FRAME_BYTES = len(config.FRAME_HEADER) + PAYLOAD_BYTES


@dataclass(frozen=True)
class Frame:
    """One raw snapshot: ADC codes for both channels."""

    v_codes: np.ndarray  # int16, len FRAME_SAMPLES
    i_codes: np.ndarray  # int16, len FRAME_SAMPLES


def parse_payload(payload: bytes) -> Frame:
    """Split a header-less payload into V/I int16 code arrays."""
    if len(payload) != PAYLOAD_BYTES:
        raise ValueError(f"expected {PAYLOAD_BYTES} payload bytes, got {len(payload)}")
    codes = np.frombuffer(payload, dtype="<i2")
    return Frame(
        v_codes=codes[: config.FRAME_SAMPLES].copy(),
        i_codes=codes[config.FRAME_SAMPLES:].copy(),
    )


class FrameParser:
    """Incremental parser: feed arbitrary byte chunks, get complete frames.

    Resynchronizes on the header, so it tolerates joining mid-stream, serial
    glitches and partial reads.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        self._buf.extend(data)
        frames: list[Frame] = []
        while True:
            start = self._buf.find(config.FRAME_HEADER)
            if start < 0:
                # Keep a tail that could be a split header, drop the rest.
                keep = len(config.FRAME_HEADER) - 1
                del self._buf[:-keep]
                break
            if start > 0:
                del self._buf[:start]
            if len(self._buf) < FRAME_BYTES:
                break
            payload = bytes(self._buf[len(config.FRAME_HEADER):FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
            frames.append(parse_payload(payload))
        return frames
