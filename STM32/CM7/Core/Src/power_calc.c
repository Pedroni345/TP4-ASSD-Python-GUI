/**
 * @file power_calc.c
 * @brief Power Calculation Implementation
 *
 * Calculates active, reactive, and apparent power from harmonics,
 * RMS values, and time-domain samples. Computes power factors and THD.
 *
 * Reference:
 * - power_analyzer/dsp/power_calc.py: Python implementation
 * - IEC 61000-4-30: Standard definitions for power quantities
 * - TP4_ASSD.pdf: Power calculation specifications
 */

#include "power_calc.h"
#include <math.h>
#include <string.h>

/* ============================================================================
 * RMS CALCULATION
 * ========================================================================== */

float32_t power_calc_rms(const float32_t *signal, uint16_t n_samples)
{
    if (!signal || n_samples == 0) {
        return 0.0f;
    }

    float32_t rms_value = 0.0f;

    /* Use CMSIS arm_rms_f32 for efficient calculation */
    arm_rms_f32((float32_t *)signal, n_samples, &rms_value);

    return rms_value;
}

void power_calc_rms_dual(
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t *vrms,
    float32_t *irms
)
{
    if (!v_signal || !i_signal || !vrms || !irms || n_samples == 0) {
        return;
    }

    *vrms = power_calc_rms(v_signal, n_samples);
    *irms = power_calc_rms(i_signal, n_samples);
}

/* ============================================================================
 * ACTIVE & REACTIVE POWER FROM PHASORS
 * ========================================================================== */

void power_calc_from_phasors(
    const ComplexPhasor_t *v_phasor,
    const ComplexPhasor_t *i_phasor,
    float32_t *p_fund,
    float32_t *q_fund,
    float32_t *s_fund,
    float32_t *phi_rad,
    float32_t *dpf
)
{
    if (!v_phasor || !i_phasor || !p_fund || !q_fund || !s_fund || !phi_rad || !dpf) {
        return;
    }

    /**
     * Cross-product for power: conj(V) * I
     *
     * conj(V) = V_r - j*V_i
     * I       = I_r + j*I_i
     *
     * conj(V) * I = (V_r - j*V_i) * (I_r + j*I_i)
     *             = (V_r*I_r + V_i*I_i) + j(V_r*I_i - V_i*I_r)
     *
     * Real part  → Active power:    P = 0.5 * Re
     * Imag part  → Reactive power:  Q = 0.5 * Im
     */

    float32_t real_part = v_phasor->real * i_phasor->real + v_phasor->imag * i_phasor->imag;
    float32_t imag_part = v_phasor->real * i_phasor->imag - v_phasor->imag * i_phasor->real;

    /* Active and reactive power (factor of 0.5 for RMS definition) */
    *p_fund = 0.5f * real_part;
    *q_fund = 0.5f * imag_part;

    /* Magnitude of voltage and current phasors */
    float32_t v_mag = sqrtf(v_phasor->real * v_phasor->real + v_phasor->imag * v_phasor->imag);
    float32_t i_mag = sqrtf(i_phasor->real * i_phasor->real + i_phasor->imag * i_phasor->imag);

    /* Apparent power (0.5 * V * I) */
    *s_fund = 0.5f * v_mag * i_mag;

    /* Phase angle φ = atan2(Q, P) */
    *phi_rad = atan2f(*q_fund, *p_fund);

    /* Displacement power factor = cos(φ) = P / S */
    if (*s_fund > 0.0f) {
        *dpf = (*p_fund) / (*s_fund);
    } else {
        *dpf = 0.0f;
    }
}

/* ============================================================================
 * TEMPORAL POWER CALCULATION
 * ========================================================================== */

void power_calc_temporal(
    float32_t v_rms,
    float32_t i_rms,
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t *p_total,
    float32_t *s_total,
    float32_t *q_total,
    float32_t *tpf
)
{
    if (!v_signal || !i_signal || !p_total || !s_total || !q_total || !tpf || n_samples == 0) {
        return;
    }

    /**
     * Apparent power from RMS values
     * S = Vrms * Irms
     */
    *s_total = v_rms * i_rms;

    /**
     * Active power from time-domain product
     * P = mean(v[n] * i[n]) = (1/N) * Σ(v[n] * i[n])
     */
    float32_t sum_product = 0.0f;

    for (uint16_t n = 0; n < n_samples; n++) {
        sum_product += v_signal[n] * i_signal[n];
    }

    *p_total = sum_product / (float32_t)n_samples;

    /**
     * Reactive power from Pythagorean relationship
     * Q = sqrt(max(S² - P², 0))
     *
     * This is conservative (assumes all non-active power is reactive)
     * but valid for AC signals with reasonably low distortion
     */
    float32_t s_sq = (*s_total) * (*s_total);
    float32_t p_sq = (*p_total) * (*p_total);
    float32_t q_sq = s_sq - p_sq;

    if (q_sq >= 0.0f) {
        *q_total = sqrtf(q_sq);
    } else {
        *q_total = 0.0f;  /* Edge case: |P| > S (shouldn't happen) */
    }

    /**
     * Total power factor
     * TPF = P / S
     */
    if (*s_total > 0.0f) {
        *tpf = (*p_total) / (*s_total);
    } else {
        *tpf = 0.0f;
    }
}

/* ============================================================================
 * THD CALCULATION
 * ========================================================================== */

void power_calc_thd(
    const HarmonicSet_t *harmonics,
    float32_t *thd_percent,
    float32_t *harmonics_norm
)
{
    if (!harmonics || !thd_percent || !harmonics_norm) {
        return;
    }

    /**
     * THD = 100 * sqrt(sum(H_k²)) / H_1  for k=2..MAX_HARMONIC
     *
     * Procedure:
     * 1. Get fundamental magnitude (k=1)
     * 2. Sum squares of harmonics 2..23
     * 3. Calculate THD = sqrt(sum) / fund * 100
     * 4. Normalize each harmonic to fundamental
     */

    float32_t fund_mag = harmonics->harmonics[1].magnitude;

    if (fund_mag <= 0.0f) {
        *thd_percent = 0.0f;
        memset(harmonics_norm, 0, (MAX_HARMONIC + 1) * sizeof(float32_t));
        return;
    }

    /* Normalize all harmonics to fundamental */
    float32_t sum_squares = 0.0f;

    for (uint16_t k = 1; k <= MAX_HARMONIC; k++) {
        float32_t normalized = harmonics->harmonics[k].magnitude / fund_mag;
        harmonics_norm[k] = normalized;

        /* Add to sum of squares (for k >= 2) */
        if (k >= 2) {
            sum_squares += normalized * normalized;
        }
    }

    /* Calculate THD as percentage */
    *thd_percent = 100.0f * sqrtf(sum_squares);
}

/* ============================================================================
 * COMPLETE BLOCK ANALYSIS
 * ========================================================================== */

void power_calc_analyze_block(
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t f_measured,
    FFTState_t *fft_state,
    MeasurementOutput_t *result
)
{
    if (!v_signal || !i_signal || !result || n_samples == 0) {
        return;
    }

    /* Initialize result */
    memset(result, 0, sizeof(MeasurementOutput_t));

    /* 1. Calculate RMS values */
    float32_t v_rms = power_calc_rms(v_signal, n_samples);
    float32_t i_rms = power_calc_rms(i_signal, n_samples);

    result->vrms = v_rms;
    result->irms = i_rms;
    result->frequency = f_measured;

    /* 2. Calculate temporal power (time-domain) */
    power_calc_temporal(
        v_rms, i_rms, v_signal, i_signal, n_samples,
        &result->p_total, &result->s_total, &result->q_total, &result->tpf
    );

    /* 3. Extract harmonics and calculate harmonic-based power (if FFT available) */
    if (fft_state) {
        HarmonicSet_t v_harmonics, i_harmonics;

        /* Extract harmonics using FFT */
        goertzel_extract_harmonics(
            fft_state, v_signal, n_samples, f_measured, &v_harmonics
        );
        goertzel_extract_harmonics(
            fft_state, i_signal, n_samples, f_measured, &i_harmonics
        );

        /* Calculate fundamental power from phasors */
        if (v_harmonics.n_harmonics > 0 && i_harmonics.n_harmonics > 0) {
            float32_t phi_rad = 0.0f;

            power_calc_from_phasors(
                &v_harmonics.harmonics[1].phasor,
                &i_harmonics.harmonics[1].phasor,
                &result->p_fund, &result->q_fund, &result->s_fund,
                &phi_rad, &result->dpf
            );

            /* Convert phase to degrees */
            result->phi_deg = phi_rad * 180.0f / 3.14159265f;
        }

        /* Calculate THD for voltage and current */
        power_calc_thd(&v_harmonics, &result->thd_v, result->v_harmonics);
        power_calc_thd(&i_harmonics, &result->thd_i, result->i_harmonics);
    } else {
        /* No FFT: use temporal power as fundamental */
        result->p_fund = result->p_total;
        result->q_fund = result->q_total;
        result->s_fund = result->s_total;
        result->dpf = result->tpf;
        result->phi_deg = 0.0f;
        result->thd_v = 0.0f;
        result->thd_i = 0.0f;
    }

    result->n_blocks = 1;
}

/* ============================================================================
 * AVERAGING & AGGREGATION
 * ========================================================================== */

void power_calc_average_blocks(
    const MeasurementOutput_t *measurements,
    uint16_t n_measurements,
    MeasurementOutput_t *average
)
{
    if (!measurements || !average || n_measurements == 0) {
        return;
    }

    /* Initialize accumulator */
    memset(average, 0, sizeof(MeasurementOutput_t));

    uint16_t valid_count = 0;

    /**
     * Accumulate measurements
     * Skip entries with n_blocks == 0 (invalid)
     */
    for (uint16_t i = 0; i < n_measurements; i++) {
        if (measurements[i].n_blocks == 0) {
            continue;  /* Skip invalid blocks */
        }

        valid_count++;

        /* Scalar quantities */
        average->vrms += measurements[i].vrms;
        average->irms += measurements[i].irms;
        average->frequency += measurements[i].frequency;
        average->p_total += measurements[i].p_total;
        average->q_total += measurements[i].q_total;
        average->s_total += measurements[i].s_total;
        average->p_fund += measurements[i].p_fund;
        average->q_fund += measurements[i].q_fund;
        average->s_fund += measurements[i].s_fund;
        average->thd_v += measurements[i].thd_v;
        average->thd_i += measurements[i].thd_i;

        /* Phase angle (average sine/cosine to avoid circular mean issues) */
        float32_t phi_rad = measurements[i].phi_deg * 3.14159265f / 180.0f;
        average->phi_deg += sinf(phi_rad);  /* Accumulate sine component */
        average->dpf += cosf(phi_rad);      /* Accumulate cosine component */

        /* Harmonic magnitudes */
        for (uint16_t k = 0; k <= MAX_HARMONIC; k++) {
            average->v_harmonics[k] += measurements[i].v_harmonics[k];
            average->i_harmonics[k] += measurements[i].i_harmonics[k];
        }
    }

    /* Divide by count to get average */
    if (valid_count > 0) {
        float32_t inv_count = 1.0f / (float32_t)valid_count;

        average->vrms *= inv_count;
        average->irms *= inv_count;
        average->frequency *= inv_count;
        average->p_total *= inv_count;
        average->q_total *= inv_count;
        average->s_total *= inv_count;
        average->p_fund *= inv_count;
        average->q_fund *= inv_count;
        average->s_fund *= inv_count;
        average->thd_v *= inv_count;
        average->thd_i *= inv_count;
        average->n_blocks = valid_count;

        /* Recover phase angle from accumulated sine/cosine */
        float32_t avg_sin = average->phi_deg * inv_count;
        float32_t avg_cos = average->dpf * inv_count;
        float32_t avg_phi_rad = atan2f(avg_sin, avg_cos);
        average->phi_deg = avg_phi_rad * 180.0f / 3.14159265f;
        average->dpf = cosf(avg_phi_rad);  /* dpf = cos(phi) */

        /* Average harmonic magnitudes */
        for (uint16_t k = 0; k <= MAX_HARMONIC; k++) {
            average->v_harmonics[k] *= inv_count;
            average->i_harmonics[k] *= inv_count;
        }

        /* Recalculate power factors on averaged values */
        if (average->s_total > 0.0f) {
            average->tpf = average->p_total / average->s_total;
        }
        if (average->s_fund > 0.0f && average->dpf == 0.0f) {
            /* Recalculate from averaged power values */
            average->dpf = average->p_fund / average->s_fund;
        }
    }
}

/* ============================================================================
 * DEBUG & TESTING UTILITIES
 * ========================================================================== */

#if DEBUG_POWER_CALC

/**
 * @brief Print measurement results (for debugging)
 */
void power_calc_print_results(const MeasurementOutput_t *result)
{
    if (!result) {
        return;
    }

    printf("=== Power Measurement Results ===\n");
    printf("Frequency: %.2f Hz\n", (double)result->frequency);
    printf("Voltage RMS:  %.3f V\n", (double)result->vrms);
    printf("Current RMS:  %.3f A\n", (double)result->irms);

    printf("\nTotal Power (All Harmonics):\n");
    printf("  Active (P):   %.2f W\n", (double)result->p_total);
    printf("  Reactive (Q): %.2f VAR\n", (double)result->q_total);
    printf("  Apparent (S): %.2f VA\n", (double)result->s_total);
    printf("  PF:           %.3f\n", (double)result->tpf);

    printf("\nFundamental Power (50 Hz):\n");
    printf("  Active (P):   %.2f W\n", (double)result->p_fund);
    printf("  Reactive (Q): %.2f VAR\n", (double)result->q_fund);
    printf("  Apparent (S): %.2f VA\n", (double)result->s_fund);
    printf("  Phase angle:  %.1f°\n", (double)result->phi_deg);
    printf("  DPF:          %.3f\n", (double)result->dpf);

    printf("\nHarmonic Distortion:\n");
    printf("  THD_V: %.2f%%\n", (double)result->thd_v);
    printf("  THD_I: %.2f%%\n", (double)result->thd_i);

    printf("Blocks: %u\n", result->n_blocks);
}

#endif /* DEBUG_POWER_CALC */
