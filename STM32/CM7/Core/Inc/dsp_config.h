/**
 * @file dsp_config.h
 * @brief DSP Configuration Parameters for TP4-ASSD Power Analyzer
 *
 * Defines all compile-time constants for the digital signal processing pipeline.
 * Configuration mirrors the Python implementation in power_analyzer/dsp/ for consistency.
 *
 * References:
 * - TP4_ASSD.pdf: Signal processing pipeline specification
 * - power_analyzer/dsp/: Python DSP reference implementation
 */

#ifndef DSP_CONFIG_H
#define DSP_CONFIG_H

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * SAMPLING CONFIGURATION
 * ========================================================================== */

/** @defgroup ADC_Sampling ADC and Sampling Configuration
 * @{
 */

#define FS_DIGITAL              5000        /**< Digital sample rate (Hz) */
#define FS_MCU                  5000        /**< Actual STM32 sampling rate (Hz) */
#define N_SAMPLES               512         /**< Buffer size (samples per frame) */
#define SAMPLE_PERIOD_US        200         /**< 1/FS_DIGITAL in microseconds */

/* ADC Configuration */
#define ADC_BITS                16          /**< ADC resolution (bits) */
#define ADC_VREF                3.0f        /**< ADC reference voltage (±3.0V differential) */
#define ADC_FULL_SCALE          32768       /**< ADC full-scale code (2^15) */

/**@}*/

/* ============================================================================
 * HIGH-PASS FILTER CONFIGURATION (DC REMOVAL)
 * ========================================================================== */

/** @defgroup HighPassFilter High-Pass IIR Filter Parameters
 * @{
 */

#define HIGHPASS_CUTOFF         1.0f        /**< DC removal cutoff frequency (Hz) */

/**
 * High-pass filter coefficient for first-order IIR:
 * H(z) = (1 - z^-1) / (1 - r*z^-1)
 *
 * Calculated as: r = exp(-2π * fc / fs)
 *                 = exp(-2π * 1.0 / 5000)
 *                 ≈ 0.99887f
 *
 * Settling time: tau = 1 / (2π * fc) ≈ 0.159 seconds
 */
#define HIGHPASS_COEFF          0.99887f    /**< IIR pole location for 1 Hz cutoff */
#define HIGHPASS_TAU_SEC        0.159f      /**< Settling time constant (seconds) */

/**@}*/

/* ============================================================================
 * ZERO-CROSSING DETECTION CONFIGURATION
 * ========================================================================== */

/** @defgroup ZeroCrossing Zero-Crossing Detection
 * @{
 */

#define F0_NOMINAL              50.0f       /**< Nominal fundamental frequency (Hz) */
#define F0_MIN                  48.0f       /**< Minimum expected frequency (Hz) */
#define F0_MAX                  52.0f       /**< Maximum expected frequency (Hz) */

/**
 * Block sizes for cycle segmentation
 * - CYCLES_PER_BLOCK: For full measurement blocks (offline processing)
 * - LIVE_CYCLES_PER_BLOCK: For live/real-time frames (shorter blocks for lower latency)
 */
#define CYCLES_PER_BLOCK        10          /**< Cycles per measurement block */
#define LIVE_CYCLES_PER_BLOCK   1           /**< Cycles per live frame block */

/**
 * Settling behavior
 * Skip initial zero-crossings to allow filters to stabilize
 */
#define SETTLE_CROSSINGS        5           /**< Zero-crossings to skip during settling */
#define SETTLE_BLOCKS           1           /**< Blocks to skip during initialization */

/**@}*/

/* ============================================================================
 * HARMONICS & SPECTRAL ANALYSIS CONFIGURATION
 * ========================================================================== */

/** @defgroup Harmonics Harmonic Analysis
 * @{
 */

#define MAX_HARMONIC            23          /**< Highest harmonic order to extract */
#define N_HARMONICS             24          /**< Total number of harmonics (fund + 23 upper) */

/**
 * FFT Configuration for harmonic extraction
 * Using CMSIS Real FFT (arm_rfft_fast_f32)
 */
#define FFT_SIZE                512         /**< FFT length (power of 2) */
#define FFT_SIZE_LOG2           9           /**< log2(FFT_SIZE) = 9 */

/**
 * Windowing for spectral leakage reduction
 * Hann window applied to each cycle block before FFT
 */
#define WINDOW_TYPE_HANN        1           /**< Use Hann window (0=rectangular) */

/**@}*/

/* ============================================================================
 * POWER CALCULATION CONFIGURATION
 * ========================================================================== */

/** @defgroup PowerCalc Power Calculation Parameters
 * @{
 */

/**
 * Cross-product convention for reactive power sign:
 * Q = 0.5 * imag(conj(V) * I)
 *
 * This yields:
 * - Positive Q for lagging current (inductive load)
 * - Negative Q for leading current (capacitive load)
 *
 * Note: Python notebook had opposite sign convention; verified against
 * industry standard (IEC 61000-4-30) in power_calc.py:21-28
 */
#define CONJUGATE_VOLTAGE       1           /**< Use conj(V) in cross-product (0=conj(I)) */

/**@}*/

/* ============================================================================
 * AVERAGING CONFIGURATION
 * ========================================================================== */

/** @defgroup Averaging Measurement Averaging
 * @{
 */

/**
 * Per-frame averaging:
 * Final measurements are averaged over multiple processed blocks
 */
#define LIVE_AVG_FRAMES         5           /**< Frames to average for display (live mode) */
#define LIVE_AVG_BLOCKS         1           /**< Blocks per frame to average (live mode) */

/**@}*/

/* ============================================================================
 * MEASUREMENT OUTPUT CONFIGURATION
 * ========================================================================== */

/** @defgroup Output Output Frame Structure
 * @{
 */

/**
 * UART frame format for processed measurements
 * Structure mirrors Python MeasurementOutput in power_calc.py
 */
#define UART_FRAME_HEADER       0xAA55AA55  /**< UART frame synchronization header */
#define UART_FRAME_FOOTER       0x55AA55AA  /**< UART frame end marker */

/**@}*/

/* ============================================================================
 * INTERNAL CALCULATIONS (DERIVED CONSTANTS)
 * ========================================================================== */

/** @defgroup Derived Derived Constants
 * @{
 */

/**
 * Frequency resolution in FFT
 * Δf = FS / FFT_SIZE = 5000 / 512 ≈ 9.77 Hz
 */
#define FFT_FREQ_RES            (FS_DIGITAL / FFT_SIZE)

/**
 * Expected bin index for fundamental at 50 Hz
 * bin_f0 = (f0 / FS) * FFT_SIZE = (50 / 5000) * 512 ≈ 5.12
 *
 * Harmonics at: k * bin_f0 for k = 1, 2, 3, ..., 23
 */
#define BIN_F0_NOMINAL          ((uint16_t)(F0_NOMINAL * FFT_SIZE / FS_DIGITAL))

/**@}*/

/* ============================================================================
 * FEATURE FLAGS
 * ========================================================================== */

/** @defgroup Features Feature Flags
 * @{
 */

#define ENABLE_DC_BLOCKER       1           /**< Apply DC removal filter */
#define ENABLE_FFT_HARMONICS    1           /**< Extract harmonics via FFT */
#define ENABLE_TEMPORAL_RMS     1           /**< Calculate temporal RMS values */
#define ENABLE_THD_CALC         1           /**< Calculate THD */
#define ENABLE_UART_OUTPUT      1           /**< Send processed data over UART */

/**@}*/

/* ============================================================================
 * DEBUG & LOGGING
 * ========================================================================== */

/** @defgroup Debug Debug Configuration
 * @{
 */

#define DEBUG_DSP               0           /**< Enable DSP debug output */
#define DEBUG_FILTER            0           /**< Enable filter state logging */
#define DEBUG_ZERO_CROSSING     0           /**< Enable zero-crossing debug */
#define DEBUG_FFT               0           /**< Enable FFT debug output */

/**@}*/

#ifdef __cplusplus
}
#endif

#endif /* DSP_CONFIG_H */
