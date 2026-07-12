/**
 * @file filters.c
 * @brief Digital Filter Implementation for TP4-ASSD Power Analyzer
 *
 * Implements causal high-pass IIR filter using CMSIS-DSP biquad cascade.
 * Removes DC offset and low-frequency components for power analysis.
 *
 * Theory:
 * -------
 * First-order high-pass filter in Z-domain:
 *   H(z) = (1 - z^-1) / (1 - r*z^-1)
 *
 * Where: r = exp(-2π * fc / fs)
 *        fc = cutoff frequency (1 Hz from dsp_config.h)
 *        fs = sample rate (5000 Hz)
 *
 * Converted to biquad form for CMSIS:
 *   H(z) = (b0 + b1*z^-1 + b2*z^-2) / (1 + a1*z^-1 + a2*z^-2)
 *
 * Coefficients:
 *   b0 = (1 + r) / 2      ≈ 0.999435
 *   b1 = -(1 + r) / 2     ≈ -0.999435
 *   b2 = 0
 *   a1 = -r               ≈ -0.99887
 *   a2 = 0
 *
 * Settling: tau = 1 / (2π * fc) ≈ 159 ms @ 1 Hz cutoff
 *
 * Reference:
 * - power_analyzer/dsp/filters.py: dc_blocker() [lines 23-51]
 * - TI MSP430 dc_filter16.c: Hardware reference
 * - CMSIS-DSP: arm_biquad_cascade_df1_f32() documentation
 */

#include "filters.h"
#include <math.h>
#include <string.h>

/* ============================================================================
 * LOCAL CONSTANTS
 * ========================================================================== */

/**
 * Pre-calculated biquad coefficients for the high-pass filter
 * Derived from first-order transfer function with r = exp(-2π*fc/fs)
 */
static const struct {
    float32_t b0;  /**< Feed-forward tap 0 */
    float32_t b1;  /**< Feed-forward tap 1 (negated b0) */
    float32_t b2;  /**< Feed-forward tap 2 (zero) */
    float32_t a1;  /**< Feedback tap 1 (-r) */
    float32_t a2;  /**< Feedback tap 2 (zero) */
} HP_COEFF = {
    .b0 = 0.999435f,    /* (1 + r) / 2 where r ≈ 0.99887 */
    .b1 = -0.999435f,   /* -(1 + r) / 2 */
    .b2 = 0.0f,
    .a1 = -0.99887f,    /* -r where r = exp(-2π * 1.0 / 5000) */
    .a2 = 0.0f
};

/**
 * Single biquad stage (one pole in this case)
 * Passed to arm_biquad_cascade_df1_f32
 */
static const uint32_t NUM_STAGES = 1;  /* Single pole = one biquad stage */

/* ============================================================================
 * INITIALIZATION
 * ========================================================================== */

void filters_highpass_init(HighPassFilterState_t *filter)
{
    if (!filter) {
        return;
    }

    /* Clear state variables */
    memset(filter->state, 0, sizeof(filter->state));

    /* Set up coefficient array in CMSIS format: [b0, b1, b2, a1, a2] */
    filter->coeffs[0] = HP_COEFF.b0;
    filter->coeffs[1] = HP_COEFF.b1;
    filter->coeffs[2] = HP_COEFF.b2;
    filter->coeffs[3] = HP_COEFF.a1;
    filter->coeffs[4] = HP_COEFF.a2;

    /* Initialize CMSIS biquad cascade structure */
    arm_biquad_cascade_df1_init_f32(
        &filter->biquad,
        NUM_STAGES,
        (float32_t *)filter->coeffs,
        filter->state
    );
}

/* ============================================================================
 * FILTER PROCESSING
 * ========================================================================== */

void filters_highpass_apply(
    HighPassFilterState_t *filter,
    const float32_t *input,
    float32_t *output,
    uint32_t n_samples
)
{
    if (!filter || !input || !output || n_samples == 0) {
        return;
    }

    /* Apply biquad cascade (single stage for high-pass) */
    arm_biquad_cascade_df1_f32(
        &filter->biquad,
        (float32_t *)input,
        output,
        n_samples
    );
}

void filters_highpass_apply_dual(
    HighPassFilterState_t *filter_v,
    HighPassFilterState_t *filter_i,
    const float32_t *v_raw,
    const float32_t *i_raw,
    float32_t *v_filtered,
    float32_t *i_filtered,
    uint32_t n_samples
)
{
    if (!filter_v || !filter_i || !v_raw || !i_raw ||
        !v_filtered || !i_filtered || n_samples == 0) {
        return;
    }

    /* Process voltage channel */
    arm_biquad_cascade_df1_f32(
        &filter_v->biquad,
        (float32_t *)v_raw,
        v_filtered,
        n_samples
    );

    /* Process current channel */
    arm_biquad_cascade_df1_f32(
        &filter_i->biquad,
        (float32_t *)i_raw,
        i_filtered,
        n_samples
    );
}

/* ============================================================================
 * STATE MANAGEMENT
 * ========================================================================== */

void filters_highpass_reset(HighPassFilterState_t *filter)
{
    if (!filter) {
        return;
    }

    /* Clear state variables (4 elements for one biquad stage) */
    memset(filter->state, 0, sizeof(filter->state));
}

float32_t filters_highpass_get_dc_estimate(const HighPassFilterState_t *filter)
{
    if (!filter) {
        return 0.0f;
    }

    /**
     * DC estimate is derived from filter state
     * For the leaky integrator topology, the pole value represents
     * the DC component estimate. This is heuristic but useful for diagnostics.
     *
     * More precisely: DC_est ≈ state[0] / (1 - HP_COEFF.a1)
     * But we return state[0] as a proxy
     */
    return filter->state[0];
}

/* ============================================================================
 * FREQUENCY RESPONSE (FOR TESTING & VALIDATION)
 * ========================================================================== */

void filters_highpass_freqresp(
    float32_t frequency,
    float32_t *magnitude,
    float32_t *phase_deg
)
{
    if (!magnitude || !phase_deg || frequency < 0.0f) {
        return;
    }

    /**
     * Evaluate frequency response of H(z) at z = exp(j*2π*f/fs)
     *
     * H(e^jω) = (1 - e^-jω) / (1 - r*e^-jω)
     *
     * Numerator: |1 - e^-jω| = 2 * sin(ω/2)
     * Phase: -ω/2 (approximately)
     *
     * Denominator: |1 - r*e^-jω| = sqrt((1-r*cos(ω))² + (r*sin(ω))²)
     * Phase: atan2(r*sin(ω), 1-r*cos(ω))
     */

    const float32_t fs = (float32_t)FS_DIGITAL;
    const float32_t r = HIGHPASS_COEFF;
    const float32_t two_pi_f_fs = 2.0f * 3.14159265f * frequency / fs;

    /* Numerator: (1 - e^-jω) */
    float32_t num_real = 1.0f - cosf(two_pi_f_fs);
    float32_t num_imag = sinf(two_pi_f_fs);
    float32_t num_mag = sqrtf(num_real * num_real + num_imag * num_imag);
    float32_t num_phase = atan2f(num_imag, num_real);

    /* Denominator: (1 - r*e^-jω) */
    float32_t denom_real = 1.0f - r * cosf(two_pi_f_fs);
    float32_t denom_imag = r * sinf(two_pi_f_fs);
    float32_t denom_mag = sqrtf(denom_real * denom_real + denom_imag * denom_imag);
    float32_t denom_phase = atan2f(denom_imag, denom_real);

    /* H(e^jω) = Num / Denom */
    *magnitude = num_mag / denom_mag;
    *phase_deg = (num_phase - denom_phase) * 180.0f / 3.14159265f;

    /* Wrap phase to [-180, 180] */
    while (*phase_deg > 180.0f) {
        *phase_deg -= 360.0f;
    }
    while (*phase_deg < -180.0f) {
        *phase_deg += 360.0f;
    }
}

/* ============================================================================
 * TESTING UTILITIES
 * ========================================================================== */

#if DEBUG_FILTER

/**
 * @brief Debug: Print filter coefficients
 */
void filters_highpass_print_coeffs(void)
{
    printf("HP Filter Coefficients:\n");
    printf("  b0 = %.6f\n", HP_COEFF.b0);
    printf("  b1 = %.6f\n", HP_COEFF.b1);
    printf("  b2 = %.6f\n", HP_COEFF.b2);
    printf("  a1 = %.6f\n", HP_COEFF.a1);
    printf("  a2 = %.6f\n", HP_COEFF.a2);
    printf("  Settling time (tau) = %.3f s\n", 1.0f / (2.0f * 3.14159f * HIGHPASS_CUTOFF));
}

/**
 * @brief Debug: Print filter state
 */
void filters_highpass_print_state(const HighPassFilterState_t *filter)
{
    if (!filter) {
        return;
    }

    printf("HP Filter State:\n");
    for (int i = 0; i < 4; i++) {
        printf("  state[%d] = %.6f\n", i, filter->state[i]);
    }
}

#endif /* DEBUG_FILTER */
