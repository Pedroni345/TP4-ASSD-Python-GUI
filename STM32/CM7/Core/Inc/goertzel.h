/**
 * @file goertzel.h
 * @brief Harmonic Extraction using CMSIS Real FFT
 *
 * Extracts voltage and current phasors at fundamental and harmonic frequencies
 * using hardware-accelerated Real FFT from CMSIS-DSP library.
 *
 * Despite the filename "goertzel" (historical from Python implementation),
 * this implementation uses CMSIS Real FFT for better performance on STM32H7.
 *
 * References:
 * - power_analyzer/dsp/goertzel.py: Python Goertzel reference
 * - TP4_ASSD.pdf: Harmonic extraction specification
 * - CMSIS-DSP: arm_rfft_fast_f32() documentation
 */

#ifndef GOERTZEL_H
#define GOERTZEL_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"
#include "dsp_config.h"

/* ============================================================================
 * HARMONIC PHASOR REPRESENTATION
 * ========================================================================== */

/**
 * @defgroup HarmonicStructures Harmonic Phasor Data Structures
 * @{
 */

/**
 * Complex phasor (rectangular form: real + j*imaginary)
 * Represents magnitude and phase of a harmonic component
 */
typedef struct {
    float32_t real;       /**< Real component (cosine component) */
    float32_t imag;       /**< Imaginary component (sine component) */
} ComplexPhasor_t;

/**
 * Represents a single harmonic (e.g., 50 Hz fundamental, 100 Hz 2nd, etc.)
 */
typedef struct {
    uint16_t order;       /**< Harmonic order (1=fundamental, 2=2nd, etc.) */
    float32_t frequency;  /**< Frequency (Hz) */
    float32_t magnitude;  /**< Magnitude (normalized to RMS) */
    float32_t phase_rad;  /**< Phase angle (radians) */
    ComplexPhasor_t phasor; /**< Rectangular form phasor */
} Harmonic_t;

/**
 * Set of harmonics extracted from voltage or current signal
 */
typedef struct {
    Harmonic_t harmonics[MAX_HARMONIC + 1];  /**< 0=fund, 1..23=upper harmonics */
    uint16_t n_harmonics;                    /**< Number of valid harmonics */
    float32_t f_fundamental;                 /**< Measured fundamental frequency */
} HarmonicSet_t;

/**@}*/

/* ============================================================================
 * FFT STATE MANAGEMENT
 * ========================================================================== */

/**
 * FFT processing state (maintains CMSIS FFT instance)
 */
typedef struct {
    arm_rfft_fast_f32_t fft_instance;       /**< CMSIS Real FFT instance */
    float32_t fft_output[FFT_SIZE * 2];     /**< FFT output buffer (real + complex interleaved) */
    float32_t window_coeffs[FFT_SIZE];      /**< Hann window coefficients */
    uint8_t initialized;                    /**< Initialization flag */
} FFTState_t;

/* ============================================================================
 * INITIALIZATION
 * ========================================================================== */

/**
 * @brief Initialize FFT processor
 *
 * Sets up CMSIS Real FFT instance and pre-calculates Hann window coefficients.
 * Call once during system startup.
 *
 * @param[in,out] fft_state Pointer to FFT state structure
 * @return void
 *
 * Example:
 * @code
 * FFTState_t fft;
 * goertzel_init(&fft);
 * @endcode
 */
void goertzel_init(FFTState_t *fft_state);

/* ============================================================================
 * HARMONIC EXTRACTION
 * ========================================================================== */

/**
 * @brief Extract harmonics from a single signal (V or I)
 *
 * Computes Real FFT of windowed signal, then extracts magnitude and phase
 * at fundamental and harmonic frequencies.
 *
 * Processing:
 * 1. Apply Hann window to reduce spectral leakage
 * 2. Compute Real FFT (CMSIS hardware-accelerated)
 * 3. Extract harmonics at k*f_fundamental for k=1..MAX_HARMONIC
 * 4. Normalize magnitudes to RMS units
 * 5. Calculate phases from complex FFT output
 *
 * @param[in]     fft_state       FFT processor state
 * @param[in]     signal          Input time-domain samples
 * @param[in]     n_samples       Number of samples (typically 1 cycle ≈ 100 samps @ 5kHz)
 * @param[in]     f_measured      Measured fundamental frequency (Hz)
 * @param[out]    harmonics       Output harmonic set (24 harmonics)
 * @return void
 *
 * @note
 * - Input signal should be high-pass filtered (DC removed)
 * - Window reduces spectral leakage for better harmonic accuracy
 * - Magnitude is RMS (not peak), accounting for Hann window scaling
 * - Phase is relative to sine function (0° = pure sine, 90° = pure cosine)
 *
 * Example:
 * @code
 * float32_t v_block[100];  // One cycle of voltage
 * HarmonicSet_t v_harmonics;
 * goertzel_extract_harmonics(&fft, v_block, 100, 50.0f, &v_harmonics);
 * printf("V1 mag=%.3f V, phase=%.1f°\n",
 *        v_harmonics.harmonics[1].magnitude,
 *        v_harmonics.harmonics[1].phase_rad * 180.0f / 3.14159f);
 * @endcode
 */
void goertzel_extract_harmonics(
    FFTState_t *fft_state,
    const float32_t *signal,
    uint16_t n_samples,
    float32_t f_measured,
    HarmonicSet_t *harmonics
);

/* ============================================================================
 * DUAL-CHANNEL EXTRACTION (CONVENIENCE)
 * ========================================================================== */

/**
 * @brief Extract harmonics from both voltage and current signals
 *
 * Processes both channels and returns harmonics for power calculations.
 *
 * @param[in]  fft_state        FFT processor state
 * @param[in]  v_signal         Voltage samples
 * @param[in]  i_signal         Current samples
 * @param[in]  n_samples        Samples per channel
 * @param[in]  f_measured       Fundamental frequency
 * @param[out] v_harmonics      Voltage harmonic set
 * @param[out] i_harmonics      Current harmonic set
 * @return void
 */
void goertzel_extract_harmonics_dual(
    FFTState_t *fft_state,
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t f_measured,
    HarmonicSet_t *v_harmonics,
    HarmonicSet_t *i_harmonics
);

/* ============================================================================
 * PHASOR UTILITIES
 * ========================================================================== */

/**
 * @brief Get magnitude from complex phasor
 *
 * @param[in] phasor Complex phasor
 * @return Magnitude (|phasor| = sqrt(real² + imag²))
 */
static inline float32_t goertzel_phasor_magnitude(const ComplexPhasor_t *phasor)
{
    if (!phasor) return 0.0f;
    return sqrtf(phasor->real * phasor->real + phasor->imag * phasor->imag);
}

/**
 * @brief Get phase from complex phasor
 *
 * @param[in] phasor Complex phasor
 * @return Phase angle (radians, [-π, π])
 */
static inline float32_t goertzel_phasor_phase(const ComplexPhasor_t *phasor)
{
    if (!phasor) return 0.0f;
    return atan2f(phasor->imag, phasor->real);
}

/**
 * @brief Multiply two complex phasors (for power calculations)
 *
 * Result = a * b = (a_real*b_real - a_imag*b_imag) + j*(a_real*b_imag + a_imag*b_real)
 *
 * Used for: conj(V) * I = (V.real - j*V.imag) * (I.real + j*I.imag)
 *
 * @param[in]  a        First phasor
 * @param[in]  b        Second phasor
 * @param[out] result   Result (a * b)
 * @return void
 */
void goertzel_phasor_multiply(
    const ComplexPhasor_t *a,
    const ComplexPhasor_t *b,
    ComplexPhasor_t *result
);

/**
 * @brief Compute complex conjugate of a phasor
 *
 * conj(a) = a_real - j*a_imag
 *
 * @param[in]  phasor   Input phasor
 * @param[out] result   Conjugate result
 * @return void
 */
void goertzel_phasor_conjugate(
    const ComplexPhasor_t *phasor,
    ComplexPhasor_t *result
);

#ifdef __cplusplus
}
#endif

#endif /* GOERTZEL_H */
