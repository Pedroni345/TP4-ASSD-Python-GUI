#!/usr/bin/env python3
"""
Mock STM32 Measurement Generator for Testing Visualizer

Generates synthetic binary frames that mimic actual STM32 output.
Useful for testing the visualizer without hardware.

Usage:
    # Terminal 1: Create virtual serial port pair
    socat -d -d pty,raw,echo=0 pty,raw,echo=0
    # Creates /dev/pts/X and /dev/pts/Y

    # Terminal 2: Run this script pointing to one port
    python test_visualizer_mock.py /dev/pts/X

    # Terminal 3: Run visualizer pointing to the other port
    python visualizer_main.py
    # Then in GUI, select /dev/pts/Y and connect
"""

import struct
import serial
import time
import math
import argparse
import sys
from dataclasses import dataclass


@dataclass
class SyntheticMeasurement:
    """Synthetic measurement for testing"""
    vrms: float = 230.0
    irms: float = 10.0
    frequency: float = 50.0
    p_total: float = 2300.0
    q_total: float = 0.0
    s_total: float = 2300.0
    tpf: float = 1.0
    p_fund: float = 2300.0
    q_fund: float = 0.0
    s_fund: float = 2300.0
    phi_deg: float = 0.0
    dpf: float = 1.0
    thd_v: float = 0.5
    thd_i: float = 0.5
    v_harmonics: list = None  # 23 floats
    i_harmonics: list = None  # 23 floats
    n_blocks: int = 5


def create_synthetic_harmonics(distortion_factor: float = 0.0) -> tuple:
    """
    Create synthetic harmonic magnitudes.

    Args:
        distortion_factor: 0=pure sine, 0.5=50% THD, etc.

    Returns:
        (v_harmonics, i_harmonics) lists of 23 floats each
    """
    v_harmonics = [1.0]  # Fundamental always 1.0 (normalized)
    i_harmonics = [1.0]

    # Add higher harmonics with decreasing magnitude
    for h in range(2, 24):
        mag = (1.0 / h) * distortion_factor if h <= 7 else distortion_factor / (h ** 2)
        v_harmonics.append(mag)
        i_harmonics.append(mag * 0.8)  # Current harmonics slightly different

    return v_harmonics, i_harmonics


def create_frame(measurement: SyntheticMeasurement) -> bytes:
    """
    Create binary frame matching STM32 output format.

    Frame structure (matches stm32_measurement_reader.FRAME_FORMAT):
        Header (4) + Measurements (252) + Footer (4) = 260 bytes
    """
    if measurement.v_harmonics is None:
        v_harm, i_harm = create_synthetic_harmonics(measurement.thd_v / 100.0)
    else:
        v_harm = measurement.v_harmonics
        i_harm = measurement.i_harmonics

    # Little-endian, mirrors MeasurementOutput_t: 14 floats + 24f + 24f
    # harmonic arrays (index 0 unused) + n_blocks + v_gain/i_gain
    fmt = '<I' + '14f' + '24f' + '24f' + 'HBBI'

    data = struct.pack(
        fmt,
        0xAA55AA55,  # Header
        # Measurements (14 floats)
        measurement.vrms,
        measurement.irms,
        measurement.frequency,
        measurement.p_total,
        measurement.q_total,
        measurement.s_total,
        measurement.tpf,
        measurement.p_fund,
        measurement.q_fund,
        measurement.s_fund,
        measurement.phi_deg,
        measurement.dpf,
        measurement.thd_v,
        measurement.thd_i,
        0.0, *v_harm,  # 24 floats (index 0 unused)
        0.0, *i_harm,  # 24 floats (index 0 unused)
        measurement.n_blocks,  # uint16
        1,   # v_gain = 1: synthetic values are already physical, no rescale
        1,   # i_gain = 1
        0x55AA55AA  # Footer
    )

    return data


def simulate_resistive_load(ser: serial.Serial, duration: int = 60):
    """
    Simulate a pure resistive load (0° phase angle).
    """
    print(f"📊 Simulating resistive load for {duration} seconds...")
    print("   Power factor should be 1.0, Q should be ~0")

    start_time = time.time()

    while time.time() - start_time < duration:
        measurement = SyntheticMeasurement(
            vrms=230.0,
            irms=10.0,
            frequency=50.0,
            p_total=2300.0,
            q_total=0.1,  # Nearly zero for resistive
            s_total=2300.0,
            tpf=0.999,
            p_fund=2300.0,
            q_fund=0.1,
            s_fund=2300.0,
            phi_deg=0.5,  # Nearly 0 for resistive
            dpf=0.999,
            thd_v=0.3,
            thd_i=0.2,
            n_blocks=5
        )

        frame = create_frame(measurement)
        ser.write(frame)
        print(f"✓ Frame sent: P={measurement.p_total:.0f}W, Q={measurement.q_total:.1f}VAR, PF={measurement.tpf:.3f}")

        time.sleep(1.0)


def simulate_inductive_load(ser: serial.Serial, duration: int = 60):
    """
    Simulate an inductive load (leading current, positive phase angle).
    """
    print(f"📊 Simulating inductive load for {duration} seconds...")
    print("   Phase angle should be positive (~60°), Q should be positive")

    start_time = time.time()

    while time.time() - start_time < duration:
        measurement = SyntheticMeasurement(
            vrms=230.0,
            irms=15.0,  # Higher current for same power
            frequency=50.0,
            p_total=1700.0,  # 230V × 15A × cos(60°) = 1725W
            q_total=2940.0,  # 230V × 15A × sin(60°) = 2990VAR
            s_total=3450.0,  # 230V × 15A = 3450VA
            tpf=0.5,  # 1700/3450 ≈ 0.49
            p_fund=1700.0,
            q_fund=2940.0,
            s_fund=3450.0,
            phi_deg=60.0,  # 60° phase lag
            dpf=0.5,
            thd_v=0.2,
            thd_i=0.3,
            n_blocks=5
        )

        frame = create_frame(measurement)
        ser.write(frame)
        print(f"✓ Frame sent: P={measurement.p_total:.0f}W, Q={measurement.q_total:.0f}VAR, PF={measurement.tpf:.3f}, φ={measurement.phi_deg:.0f}°")

        time.sleep(1.0)


def simulate_distorted_load(ser: serial.Serial, duration: int = 60):
    """
    Simulate a nonlinear load with harmonics (e.g., rectifier).
    """
    print(f"📊 Simulating distorted load for {duration} seconds...")
    print("   THD should be 10-20%, higher harmonics visible")

    start_time = time.time()
    frame_count = 0

    while time.time() - start_time < duration:
        frame_count += 1

        # Simulate slowly varying THD
        thd = 15.0 + 5.0 * math.sin(2 * math.pi * frame_count / 30.0)

        v_harm, i_harm = create_synthetic_harmonics(thd / 100.0)

        measurement = SyntheticMeasurement(
            vrms=230.0,
            irms=12.0,
            frequency=50.0,
            p_total=2000.0,
            q_total=300.0,
            s_total=2300.0,
            tpf=0.87,
            p_fund=2000.0,
            q_fund=300.0,
            s_fund=2300.0,
            phi_deg=20.0,
            dpf=0.94,
            thd_v=thd,
            thd_i=thd * 1.2,
            v_harmonics=v_harm,
            i_harmonics=i_harm,
            n_blocks=5
        )

        frame = create_frame(measurement)
        ser.write(frame)
        print(f"✓ Frame {frame_count}: P={measurement.p_total:.0f}W, THD_V={measurement.thd_v:.1f}%, THD_I={measurement.thd_i:.1f}%")

        time.sleep(1.0)


def simulate_manual_input(ser: serial.Serial):
    """
    Allow user to manually create custom measurements.
    """
    print("\n📝 Manual Measurement Input Mode")
    print("   Enter measurement values (or press Enter for defaults)")
    print("   Type 'quit' to exit, 'send' to transmit frame\n")

    measurement = SyntheticMeasurement()

    while True:
        try:
            # Allow user to set values
            vrms_str = input(f"Voltage RMS [{measurement.vrms}V]: ").strip()
            if vrms_str.lower() == 'quit':
                break
            if vrms_str and vrms_str != 'send':
                measurement.vrms = float(vrms_str)

            irms_str = input(f"Current RMS [{measurement.irms}A]: ").strip()
            if irms_str and irms_str != 'send':
                measurement.irms = float(irms_str)

            phi_str = input(f"Phase Angle [{measurement.phi_deg}°]: ").strip()
            if phi_str and phi_str != 'send':
                measurement.phi_deg = float(phi_str)

            thd_str = input(f"Voltage THD [{measurement.thd_v}%]: ").strip()
            if thd_str and thd_str != 'send':
                measurement.thd_v = float(thd_str)

            # Calculate power from V, I, and phase
            measurement.p_total = measurement.vrms * measurement.irms * math.cos(math.radians(measurement.phi_deg))
            measurement.q_total = measurement.vrms * measurement.irms * math.sin(math.radians(measurement.phi_deg))
            measurement.s_total = measurement.vrms * measurement.irms
            measurement.tpf = measurement.p_total / measurement.s_total if measurement.s_total > 0 else 0

            # Send frame
            frame = create_frame(measurement)
            ser.write(frame)
            print(f"✓ Sent: {measurement.vrms:.0f}V @ {measurement.irms:.1f}A, φ={measurement.phi_deg:.0f}°, P={measurement.p_total:.0f}W\n")

        except ValueError as e:
            print(f"❌ Invalid input: {e}")
        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Mock STM32 measurement generator for visualizer testing"
    )
    parser.add_argument(
        "port",
        help="Serial port to write to (e.g., /dev/pts/X or COM3)"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["resistive", "inductive", "distorted", "manual", "continuous"],
        default="resistive",
        help="Simulation mode (default: resistive)"
    )
    parser.add_argument(
        "-d", "--duration",
        type=int,
        default=60,
        help="Duration in seconds for automatic modes (default: 60)"
    )
    parser.add_argument(
        "-b", "--baudrate",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)"
    )

    args = parser.parse_args()

    print("="*60)
    print("TP4-ASSD Mock STM32 Generator")
    print("="*60)
    print(f"Port: {args.port}")
    print(f"Baud: {args.baudrate}")
    print(f"Mode: {args.mode}")
    print("="*60)

    try:
        ser = serial.Serial(args.port, args.baudrate, timeout=1)
        print(f"✓ Connected to {args.port}\n")

        if args.mode == "resistive":
            simulate_resistive_load(ser, args.duration)
        elif args.mode == "inductive":
            simulate_inductive_load(ser, args.duration)
        elif args.mode == "distorted":
            simulate_distorted_load(ser, args.duration)
        elif args.mode == "manual":
            simulate_manual_input(ser)
        elif args.mode == "continuous":
            print("🔄 Continuous mode: Press Ctrl+C to stop")
            simulate_resistive_load(ser, 9999)

    except serial.SerialException as e:
        print(f"❌ Serial error: {e}")
        print("\nTip: Use socat to create virtual serial ports:")
        print("  socat -d -d pty,raw,echo=0 pty,raw,echo=0")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⏹ Interrupted by user")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("✓ Serial port closed")


if __name__ == "__main__":
    main()
