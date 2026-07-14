"""
STM32 Power Analyzer - Binary Measurement Frame Reader

Receives processed power measurements from STM32 over UART.
Format: Binary struct (header + 200 bytes data + footer)
"""

import struct
import serial
from typing import Optional, NamedTuple
from dataclasses import dataclass


@dataclass
class PowerMeasurement:
    """Processed power measurement from STM32 DSP pipeline"""
    vrms: float              # Voltage RMS (V)
    irms: float              # Current RMS (A)
    frequency: float         # Fundamental frequency (Hz)
    p_total: float           # Total active power (W)
    q_total: float           # Total reactive power (VAR)
    s_total: float           # Total apparent power (VA)
    tpf: float               # Total power factor
    p_fund: float            # Fundamental active power (W)
    q_fund: float            # Fundamental reactive power (VAR)
    s_fund: float            # Fundamental apparent power (VA)
    phi_deg: float           # Fundamental phase angle (degrees)
    dpf: float               # Displacement power factor
    thd_v: float             # Voltage THD (%)
    thd_i: float             # Current THD (%)
    v_harmonics: list        # V_k/V_1 normalized [0..22]
    i_harmonics: list        # I_k/I_1 normalized [0..22]
    n_blocks: int            # Number of blocks averaged


class STM32Reader:
    """
    Reads processed measurement frames from STM32 over UART.

    Binary Protocol:
    ┌──────────────────────────────────────────┐
    │ Header:         0xAA55AA55     (4 bytes) │
    │ Vrms, Irms, Frequency          (12 bytes)│
    │ P_total, Q_total, S_total      (12 bytes)│
    │ TPF, P_fund, Q_fund, S_fund    (16 bytes)│
    │ Phi_deg, DPF, THD_V, THD_I     (16 bytes)│
    │ V_harmonics[23]                (92 bytes)│
    │ I_harmonics[23]                (92 bytes)│
    │ N_blocks, Reserved             (4 bytes) │
    │ Footer:         0x55AA55AA     (4 bytes) │
    ├──────────────────────────────────────────┤
    │ Total:                        (~200 bytes)│
    └──────────────────────────────────────────┘
    """

    # Binary struct format (adjust based on actual C struct layout)
    # 'I' = uint32 (header)
    # '23f' = 23×float32 (V_harmonics)
    # '23f' = 23×float32 (I_harmonics)
    # 'HHI' = uint16, uint16, uint32 (n_blocks, reserved, footer)
    FRAME_FORMAT = '!I3f3f4f4f23f23fHHI'  # Packed binary
    FRAME_SIZE = 204  # bytes (will adjust after testing)

    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 115200, timeout: float = 2.0):
        """
        Initialize STM32 measurement reader.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' on Linux, 'COM3' on Windows)
            baudrate: UART baud rate (default 115200)
            timeout: Serial read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial = None
        self.frame_count = 0
        self.error_count = 0

    def connect(self) -> bool:
        """Open serial connection to STM32"""
        try:
            self.serial = serial.Serial(
                self.port,
                self.baudrate,
                timeout=self.timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS
            )
            print(f"✓ Connected to {self.port} @ {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"✗ Failed to open {self.port}: {e}")
            return False

    def disconnect(self):
        """Close serial connection"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None
            print("✓ Disconnected from STM32")

    def read_frame(self) -> Optional[PowerMeasurement]:
        """
        Read and parse one measurement frame from STM32.

        Synchronizes to frame boundaries by looking for header pattern.

        Returns:
            PowerMeasurement object on success, None on error
        """
        if not self.serial or not self.serial.is_open:
            print("✗ Serial port not open")
            return None

        try:
            # Sync to frame start (0xAA55AA55)
            header = self._sync_to_header()
            if header is None:
                return None

            # Read rest of frame (frame size minus header already read)
            frame_payload = self.serial.read(self.FRAME_SIZE - 4)

            if len(frame_payload) < self.FRAME_SIZE - 4:
                self.error_count += 1
                print(f"⚠ Incomplete frame: {len(frame_payload)} bytes")
                return None

            # Combine header with payload
            full_frame = struct.pack('!I', header) + frame_payload

            # Parse binary structure
            try:
                parsed = struct.unpack(self.FRAME_FORMAT, full_frame)
            except struct.error as e:
                self.error_count += 1
                print(f"✗ Struct unpack failed: {e}")
                return None

            # Extract fields
            header_val = parsed[0]
            vrms, irms, frequency = parsed[1:4]
            p_total, q_total, s_total = parsed[4:7]
            tpf, p_fund, q_fund, s_fund = parsed[7:11]
            phi_deg, dpf, thd_v, thd_i = parsed[11:15]
            v_harmonics = list(parsed[15:38])  # 23 floats
            i_harmonics = list(parsed[38:61])  # 23 floats
            n_blocks, reserved, footer = parsed[61:64]

            # Verify frame boundaries
            if header_val != 0xAA55AA55:
                self.error_count += 1
                print(f"✗ Invalid header: {hex(header_val)}")
                return None

            if footer != 0x55AA55AA:
                self.error_count += 1
                print(f"⚠ Invalid footer: {hex(footer)}")
                # Don't fail on footer, it might be struct packing issue

            # Create measurement object
            self.frame_count += 1

            return PowerMeasurement(
                vrms=vrms,
                irms=irms,
                frequency=frequency,
                p_total=p_total,
                q_total=q_total,
                s_total=s_total,
                tpf=tpf,
                p_fund=p_fund,
                q_fund=q_fund,
                s_fund=s_fund,
                phi_deg=phi_deg,
                dpf=dpf,
                thd_v=thd_v,
                thd_i=thd_i,
                v_harmonics=v_harmonics,
                i_harmonics=i_harmonics,
                n_blocks=n_blocks
            )

        except Exception as e:
            self.error_count += 1
            print(f"✗ Frame read error: {e}")
            return None

    def _sync_to_header(self) -> Optional[int]:
        """
        Synchronize to frame header (0xAA55AA55).

        Reads bytes until finding the 4-byte header pattern.

        Returns:
            Header value (0xAA55AA55) on success, None on timeout
        """
        buf = b''
        max_attempts = 1000
        attempts = 0

        while attempts < max_attempts:
            b = self.serial.read(1)
            if not b:
                return None  # Timeout

            buf = (buf + b)[-4:]  # Keep last 4 bytes

            if buf == b'\xaa\x55\xaa\x55':
                return 0xAA55AA55

            attempts += 1

        print(f"✗ Header sync timeout after {max_attempts} attempts")
        return None

    def get_stats(self) -> dict:
        """Get reader statistics"""
        return {
            'frames_read': self.frame_count,
            'errors': self.error_count,
            'success_rate': 100 * self.frame_count / max(1, self.frame_count + self.error_count)
        }


def main():
    """Example usage: continuous reading and display"""
    reader = STM32Reader('/dev/ttyUSB0', baudrate=115200)

    if not reader.connect():
        return

    print("\n" + "="*70)
    print("STM32 Power Analyzer - Live Measurement Display")
    print("="*70)

    try:
        frame_num = 0
        while True:
            measurement = reader.read_frame()

            if measurement:
                frame_num += 1
                print(f"\n[Frame #{frame_num}] Blocks: {measurement.n_blocks}")
                print(f"  Voltage:  {measurement.vrms:8.2f} V RMS  |  THD: {measurement.thd_v:5.2f}%")
                print(f"  Current:  {measurement.irms:8.3f} A RMS  |  THD: {measurement.thd_i:5.2f}%")
                print(f"  Frequency: {measurement.frequency:7.2f} Hz  |  Phase: {measurement.phi_deg:+7.1f}°")
                print(f"  Power:    P={measurement.p_total:9.1f} W  |  Q={measurement.q_total:+9.1f} VAR")
                print(f"  Apparent: S={measurement.s_total:9.1f} VA  |  PF={measurement.tpf:6.3f}")
                print(f"  Fundamental: P={measurement.p_fund:8.1f}W | Q={measurement.q_fund:+8.1f}VAR | S={measurement.s_fund:8.1f}VA | DPF={measurement.dpf:.3f}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")

    finally:
        stats = reader.get_stats()
        print(f"\n{'='*70}")
        print(f"Statistics: {stats['frames_read']} frames read, {stats['errors']} errors")
        print(f"Success rate: {stats['success_rate']:.1f}%")
        reader.disconnect()


if __name__ == "__main__":
    main()
