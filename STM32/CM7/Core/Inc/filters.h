/**
 * @file filters.h
 * @brief Digital Filter Interface for TP4-ASSD Power Analyzer
 *
 * Implements causal high-pass IIR filter for DC removal, using CMSIS-DSP.
 * Replaces Python dc_blocker() from filters.py for real-time hardware processing.
 *
 * References:
 * - power_analyzer/dsp/filters.py: Python reference implementation
 * - TI MSP430 dc_filter16.c: Hardware reference
 * - CMSIS-DSP: arm_biquad_cascade_df1_f32()
 */

#ifndef FILTERS_H
#define FILTERS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"
#include "dsp_config.h"

/* ============================================================================
 * HIGH-PASS FILTER STATE
 * ========================================================================== */

/**
 * @defgroup HighPassFilter High-Pass IIR Filter State
 * @{
 */

/**
 * High-pass filter instance for a single channel (V or I)
 *
 * Implements: H(z) = (1 - z^-1) / (1 - r*z^-1)
 *
 * Converted to biquad (second-order section) form for CMSIS compatibility:
 * H(z) = (b0 + b1*z^-1 + b2*z^-2) / (1 + a1*z^-1 + a2*z^-2)
 *
 * For a single-pole high-pass:
 * - b0 = (1+r) / 2
 * - b1 = -(1+r) / 2
 * - b2 = 0
 * - a1 = -r
 * - a2 = 0
 */
typedef struct {
    arm_biquad_casd_df1_inst_f32 biquad;    /**< CMSIS biquad cascade state */
    float32_t coeffs[5];                    /**< Biquad coefficients [b0, b1, b2, a1, a2] */
    float32_t state[4];                     /**< Filter state variables */
} HighPassFilterState_t;

/**@}*/

/* ============================================================================
 * FILTER INITIALIZATION
 * ========================================================================== */

/**
 * @brief Initialize high-pass filter for a single channel
 *
 * Sets up a first-order IIR high-pass filter with cutoff frequency
 * defined in dsp_config.h (HIGHPASS_CUTOFF).
 *
 * @param[in,out] filter Pointer to filter state structure
 *
 * @return void
 *
 * @note Call once during system initialization for each channel (V, I)
 *
 * Example:
 * @code
 * HighPassFilterState_t filter_v, filter_i;
 * filters_highpass_init(&filter_v);
 * filters_highpass_init(&filter_i);
 * @endcode
 */
void filters_highpass_init(HighPassFilterState_t *filter);

/* ============================================================================
 * FILTER PROCESSING
 * ========================================================================== */

/**
 * @brief Apply high-pass filter to a block of samples
 *
 * Processes input samples through the initialized IIR filter state,
 * maintaining state between calls for continuous DC removal.
 *
 * @param[in,out] filter    Pointer to filter state (updated after call)
 * @param[in]  input        Input sample buffer (float32)
 * @param[out] output       Filtered output buffer (float32)
 * @param[in]  n_samples    Number of samples to process
 *
 * @return void
 *
 * @note
 * - State is maintained between calls (do not reset between frames)
 * - Settling time ~160 ms (tau = 1 / (2π * 1 Hz))
 * - Memory layout: input and output must not overlap
 *
 * Example:
 * @code
 * float32_t v_raw[512], v_filtered[512];
 * filters_highpass_apply(&filter_v, v_raw, v_filtered, 512);
 * @endcode
 */
void filters_highpass_apply(
    HighPassFilterState_t *filter,
    const float32_t *input,
    float32_t *output,
    uint32_t n_samples
);

/**
 * @brief Apply high-pass filter to voltage and current channels simultaneously
 *
 * Convenience function for filtering both channels in one call.
 * Slightly more efficient than calling filters_highpass_apply twice.
 *
 * @param[in,out] filter_v  Voltage channel filter state
 * @param[in,out] filter_i  Current channel filter state
 * @param[in]  v_raw        Voltage input buffer
 * @param[in]  i_raw        Current input buffer
 * @param[out] v_filtered   Voltage output buffer
 * @param[out] i_filtered   Current output buffer
 * @param[in]  n_samples    Number of samples per channel
 *
 * @return void
 */
void filters_highpass_apply_dual(
    HighPassFilterState_t *filter_v,
    HighPassFilterState_t *filter_i,
    const float32_t *v_raw,
    const float32_t *i_raw,
    float32_t *v_filtered,
    float32_t *i_filtered,
    uint32_t n_samples
);

/* ============================================================================
 * FILTER STATE MANAGEMENT
 * ========================================================================== */

/**
 * @brief Reset filter state to zero (clear history)
 *
 * Clears all state variables. Useful for:
 * - Resetting after long idle periods
 * - Changing operating modes
 * - Clearing initial transients
 *
 * @param[in,out] filter Pointer to filter state
 * @return void
 *
 * @warning After reset, filter needs ~160 ms settling time before
 *          measurements become valid.
 */
void filters_highpass_reset(HighPassFilterState_t *filter);

/**
 * @brief Get current DC estimate from filter state
 *
 * The high-pass filter maintains an estimate of the DC component
 * in its integrator state. This function retrieves that estimate.
 *
 * @param[in] filter Pointer to filter state
 * @return DC offset estimate (physical units)
 *
 * @note Used for diagnostics and adaptive gain control
 */
float32_t filters_highpass_get_dc_estimate(const HighPassFilterState_t *filter);

/* ============================================================================
 * FREQUENCY RESPONSE (FOR TESTING)
 * ========================================================================== */

/**
 * @brief Calculate frequency response of high-pass filter
 *
 * Computes magnitude and phase response at a given frequency.
 * Used for filter validation and frequency response plots.
 *
 * @param[in]  frequency   Test frequency (Hz)
 * @param[out] magnitude   Filter magnitude response (linear, not dB)
 * @param[out] phase_deg   Filter phase response (degrees)
 *
 * @return void
 */
void filters_highpass_freqresp(
    float32_t frequency,
    float32_t *magnitude,
    float32_t *phase_deg
);

#ifdef __cplusplus
}
#endif

#endif /* FILTERS_H */
