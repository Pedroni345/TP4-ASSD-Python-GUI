"""Global constants for the power-analyzer simulator.

Values come from the TP4-ASSD hardware design (PA.ipynb schematics) and the
DSP notebook. Keeping them here makes the rest of the package configuration
free and easy to extend (see PDF "Trabajo Futuro").
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Sampling chain
# --------------------------------------------------------------------------
FS_ANALOG = 100_000.0          # "analog" oversampling rate used to fake v(t), i(t)
FS_DIGITAL = 5_000.0           # ADC sample rate after decimation
DECIMATION = int(FS_ANALOG / FS_DIGITAL)

# --------------------------------------------------------------------------
# ADC (MCP3313LD-05)
# --------------------------------------------------------------------------
ADC_BITS = 16                  # notebook references -96.3 dB ~= 16 bit
ADC_VREF = 3.0                 # volts; differential full scale is +/- VREF

# --------------------------------------------------------------------------
# PGA281A programmable-gain amplifier ranges (from the schematics).
# Each entry: gain code -> peak input that maps to +/- VREF at the ADC.
# "peak" is the absolute peak (so +/- peak fills the whole ADC range).
# --------------------------------------------------------------------------
VOLTAGE_GAINS = {
    "G2": 735.0,
    "G4": 368.0,
    "G8": 185.0,
    "G16": 92.0,
    "G32": 46.0,
    "G64": 23.0,
}

CURRENT_GAINS = {
    "G4": 12.5,
    "G8": 6.25,
    "G16": 3.13,
    "G32": 1.5,
    "G64": 0.8,
}

DEFAULT_VOLTAGE_GAIN = "G2"    # +/- 735 V range
DEFAULT_CURRENT_GAIN = "G4"    # +/- 12.5 A range

# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------
ANTIALIAS_CUTOFF = 2_000.0     # Hz, analog low-pass before the ADC
ANTIALIAS_ORDER = 4
HIGHPASS_CUTOFF = 1.0          # Hz, digital DC-removal high-pass
HIGHPASS_ORDER = 2

# --------------------------------------------------------------------------
# Signal / measurement defaults
# --------------------------------------------------------------------------
F0_DEFAULT = 50.0              # mains fundamental
CYCLES_PER_BLOCK = 10          # zero-crossing block length
SETTLE_CROSSINGS = 5          # discard first crossings while filters settle
MAX_HARMONIC = 23             # highest harmonic order handled (notebook used ~23)

# Notebook default "real" signal --------------------------------------------
# Voltage: 325 V fundamental + DC offset + harmonic list (index 0 -> 2nd harmonic)
V_FUND_DEFAULT = 325.0
V_DC_DEFAULT = 10.0
V_HARMONIC_AMPS_DEFAULT = [3, 40, 3, 25, 2, 15, 2, 10, 2, 5, 1, 5, 1, 5, 1, 4, 1, 4, 1, 4, 1, 3]
V_NOISE_DEFAULT = 10.0

# Current: kept within the hardware's largest current range (G4 = +/- 12.5 A).
# (The notebook used 15 A, which the real shunt front-end cannot represent;
#  the core DSP is still validated against the notebook in the tests.)
I_FUND_DEFAULT = 7.0
I_DC_DEFAULT = 1.0
I_THIRD_DEFAULT = 1.5
I_NOISE_DEFAULT = 0.3
PHASE_LAG_DEFAULT = 30.0       # degrees (pi/6)
