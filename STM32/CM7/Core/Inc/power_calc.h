/**
 * @file power_calc.h
 * @brief Power Calculation and Analysis
 *
 * Calculates active, reactive, and apparent power; power factors; and
 * total harmonic distortion from extracted harmonics and RMS values.
 *
 * Theory:
 * -------
 * Power calculations use both harmonic (frequency-domain) and temporal
 * (time-domain) approaches:
 *
 * 1. Fundamental Power (from Goertzel phasors):
 *    P_fund = 0.5 * Re(conj(V_1) * I_1)
 *    Q_fund = 0.5 * Im(conj(V_1) * I_1)
 *    S_fund = 0.5 * |V_1| * |I_1|
 *    DPF = cos(φ) = P_fund / S_fund
 *
 * 2. Total Power (all harmonics + temporal):
 *    P_total = mean(v[n] * i[n])     (time-domain power)
 *    S_total = Vrms * Irms           (apparent power)
 *    Q_total = sqrt(max(S² - P², 0)) (reactive power)
 *    TPF = P_total / S_total
 *
 * 3. THD (Total Harmonic Distortion):
 *    THD = 100 * sqrt(sum(V_k²)) / V_1  for k=2..23
 *
 * References:
 * - power_analyzer/dsp/power_calc.py: Python reference implementation
 * - TP4_ASSD.pdf: Power calculation specifications
 * - IEC 61000-4-30: Standard power measurement definitions
 */

#ifndef POWER_CALC_H
#define POWER_CALC_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"
#include "dsp_config.h"
#include "goertzel.h"

/* ============================================================================
 * MEASUREMENT RESULT STRUCTURE
 * ========================================================================== */

/**
 * @defgroup PowerMeasurements Power Measurement Results
 * @{
 */

/**
 * Complete set of power measurements for one analysis block
 *
 * Mirrors Python Measurements dataclass from power_calc.py
 */
typedef struct {
    /* RMS Values */
    float32_t vrms;             /**< Voltage RMS (V) */
    float32_t irms;             /**< Current RMS (A) */

    /* System Frequency */
    float32_t frequency;        /**< Fundamental frequency (Hz) */

    /* Power (All Harmonics) */
    float32_t p_total;          /**< Total active power (W) - all harmonics */
    float32_t q_total;          /**< Total reactive power (VAR) - all harmonics */
    float32_t s_total;          /**< Total apparent power (VA) - all harmonics */
    float32_t tpf;              /**< Total power factor = p_total / s_total */

    /* Fundamental Power Only */
    float32_t p_fund;           /**< Fundamental active power (W) */
    float32_t q_fund;           /**< Fundamental reactive power (VAR) */
    float32_t s_fund;           /**< Fundamental apparent power (VA) */
    float32_t phi_deg;          /**< Fundamental phase angle (degrees) */
    float32_t dpf;              /**< Displacement power factor = cos(phi) */

    /* Harmonic Distortion */
    float32_t thd_v;            /**< Voltage THD (%) */
    float32_t thd_i;            /**< Current THD (%) */

    /* Normalized Harmonic Magnitudes */
    float32_t v_harmonics[MAX_HARMONIC + 1];  /**< V_k / V_1 for k=1..23 */
    float32_t i_harmonics[MAX_HARMONIC + 1];  /**< I_k / I_1 for k=1..23 */

    /* Metadata */
    uint16_t n_blocks;          /**< Number of blocks averaged */
} MeasurementOutput_t;

/**@}*/

/* ============================================================================
 * RMS CALCULATION
 * ========================================================================== */

/**
 * @brief Calculate RMS value of a signal block
 *
 * Uses CMSIS arm_rms_f32 for efficient RMS calculation.
 *
 * @param[in] signal        Input signal samples
 * @param[in] n_samples     Number of samples
 * @return RMS value
 *
 * Example:
 * @code
 * float32_t rms = power_calc_rms(v_filtered, 100);
 * printf("V_rms = %.3f V\n", rms);
 * @endcode
 */
float32_t power_calc_rms(const float32_t *signal, uint16_t n_samples);

/**
 * @brief Calculate RMS for both voltage and current channels
 *
 * @param[in]  v_signal    Voltage samples
 * @param[in]  i_signal    Current samples
 * @param[in]  n_samples   Samples per channel
 * @param[out] vrms        Voltage RMS
 * @param[out] irms        Current RMS
 * @return void
 */
void power_calc_rms_dual(
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t *vrms,
    float32_t *irms
);

/* ============================================================================
 * ACTIVE & REACTIVE POWER (FROM PHASORS)
 * ========================================================================== */

/**
 * @brief Calculate active and reactive power from voltage and current phasors
 *
 * Uses fundamental harmonic (1st order) phasors to compute:
 * - Active power P = 0.5 * Re(conj(V) * I)
 * - Reactive power Q = 0.5 * Im(conj(V) * I)
 * - Apparent power S = 0.5 * |V| * |I|
 * - Phase angle φ = atan2(Q, P)
 * - Displacement PF = P / S = cos(φ)
 *
 * Convention: conj(V) * I yields positive Q for lagging current (inductive)
 *
 * @param[in]  v_phasor    Voltage phasor (rectangular: real + j*imag)
 * @param[in]  i_phasor    Current phasor
 * @param[out] p_fund      Fundamental active power (W)
 * @param[out] q_fund      Fundamental reactive power (VAR)
 * @param[out] s_fund      Fundamental apparent power (VA)
 * @param[out] phi_rad     Phase angle (radians)
 * @param[out] dpf         Displacement power factor
 * @return void
 *
 * Example:
 * @code
 * float32_t p_fund, q_fund, s_fund, phi_rad, dpf;
 * power_calc_from_phasors(
 *     &v_harmonics.harmonics[1].phasor,
 *     &i_harmonics.harmonics[1].phasor,
 *     &p_fund, &q_fund, &s_fund, &phi_rad, &dpf
 * );
 * @endcode
 */
void power_calc_from_phasors(
    const ComplexPhasor_t *v_phasor,
    const ComplexPhasor_t *i_phasor,
    float32_t *p_fund,
    float32_t *q_fund,
    float32_t *s_fund,
    float32_t *phi_rad,
    float32_t *dpf
);

/* ============================================================================
 * TEMPORAL POWER (RMS-BASED)
 * ========================================================================== */

/**
 * @brief Calculate temporal (time-domain) power metrics
 *
 * Computes active and apparent power from RMS values and average product.
 *
 * @param[in]  v_rms       Voltage RMS (V)
 * @param[in]  i_rms       Current RMS (A)
 * @param[in]  v_signal    Voltage samples
 * @param[in]  i_signal    Current samples
 * @param[in]  n_samples   Samples per channel
 * @param[out] p_total     Total active power (W)
 * @param[out] s_total     Total apparent power (VA)
 * @param[out] q_total     Total reactive power (VAR)
 * @param[out] tpf         Total power factor
 * @return void
 *
 * Note: Reactive power computed as Q = sqrt(max(S² - P², 0))
 */
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
);

/* ============================================================================
 * THD CALCULATION
 * ========================================================================== */

/**
 * @brief Calculate Total Harmonic Distortion (THD)
 *
 * THD = 100 * sqrt(sum(H_k²)) / H_1  for k=2..MAX_HARMONIC
 *
 * Where H_k is the magnitude of the k-th harmonic.
 *
 * @param[in]  harmonics       Extracted harmonics set
 * @param[out] thd_percent     THD value (%)
 * @param[out] harmonics_norm  Normalized harmonic magnitudes (H_k / H_1)
 * @return void
 *
 * Example:
 * @code
 * float32_t thd_v;
 * float32_t v_harmonics_norm[24];
 * power_calc_thd(&v_harmonics, &thd_v, v_harmonics_norm);
 * printf("V THD = %.2f%%\n", thd_v);
 * @endcode
 */
void power_calc_thd(
    const HarmonicSet_t *harmonics,
    float32_t *thd_percent,
    float32_t *harmonics_norm
);

/* ============================================================================
 * COMPLETE BLOCK ANALYSIS
 * ========================================================================== */

/**
 * @brief Analyze a single cycle block (complete processing)
 *
 * Performs all power calculations on one AC cycle worth of samples:
 * - Calculate RMS values
 * - Extract harmonics (if fft_state provided)
 * - Calculate active/reactive/apparent power
 * - Calculate THD and phase angle
 *
 * @param[in]     v_signal      Voltage samples (one cycle)
 * @param[in]     i_signal      Current samples (one cycle)
 * @param[in]     n_samples     Samples in block
 * @param[in]     f_measured    Measured fundamental frequency (Hz)
 * @param[in,out] fft_state     FFT processor (NULL = skip harmonic extraction)
 * @param[out]    result        Analysis result
 * @return void
 */
void power_calc_analyze_block(
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t f_measured,
    FFTState_t *fft_state,
    MeasurementOutput_t *result
);

/* ============================================================================
 * AVERAGING & AGGREGATION
 * ========================================================================== */

/**
 * @brief Average measurements from multiple blocks
 *
 * Aggregates individual block results into a single measurement:
 * - Average RMS, power, frequency, THD across blocks
 * - Average harmonic magnitudes
 * - Recalculate power factors on averaged values
 *
 * @param[in]  measurements    Array of per-block measurements
 * @param[in]  n_measurements  Number of blocks
 * @param[out] average         Averaged result
 * @return void
 *
 * Note: Only blocks with n_blocks > 0 are included in average
 */
void power_calc_average_blocks(
    const MeasurementOutput_t *measurements,
    uint16_t n_measurements,
    MeasurementOutput_t *average
);

#ifdef __cplusplus
}
#endif

#endif /* POWER_CALC_H */
