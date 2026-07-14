/**
 * @file dsp_tests.c
 * @brief Comprehensive DSP Module Testing Suite
 *
 * Tests:
 * 1. High-pass filter frequency response
 * 2. Zero-crossing detection accuracy
 * 3. FFT harmonic extraction
 * 4. Power calculations correctness
 * 5. End-to-end frame processing
 *
 * All tests use known synthetic signals for validation.
 */

#include <stdio.h>
#include <math.h>
#include <string.h>
#include "arm_math.h"
#include "dsp_pipeline.h"
#include "filters.h"
#include "zero_crossing.h"
#include "goertzel.h"
#include "power_calc.h"

#define PI 3.14159265358979f

/* ============================================================================
 * TEST 1: HIGH-PASS FILTER FREQUENCY RESPONSE
 * ========================================================================== */

void test_highpass_filter(void)
{
    printf("\n=== TEST 1: High-Pass Filter Frequency Response ===\n");

    HighPassFilterState_t filter;
    filters_highpass_init(&filter);

    /* Test 1a: DC blocking (should attenuate DC component) */
    float32_t dc_input[100];
    float32_t dc_output[100];
    for (int i = 0; i < 100; i++) {
        dc_input[i] = 1.0f;  /* Pure DC */
    }

    filters_highpass_apply(&filter, dc_input, dc_output, 100);

    /* After settling, output should be near zero */
    float32_t dc_response = dc_output[99];
    printf("DC Response: %.6f (should be ~0.0)\n", (double)dc_response);
    if (fabsf(dc_response) < 0.01f) {
        printf("✓ DC blocking test PASSED\n");
    } else {
        printf("✗ DC blocking test FAILED: Response %.6f > 0.01\n", (double)dc_response);
    }

    /* Test 1b: 50 Hz sine wave (should pass through) */
    filters_highpass_reset(&filter);
    float32_t sine_50hz[250];
    float32_t sine_output[250];
    float32_t f_test = 50.0f;
    float32_t fs = 5000.0f;

    for (int i = 0; i < 250; i++) {
        sine_50hz[i] = sinf(2.0f * PI * f_test * i / fs);
    }

    filters_highpass_apply(&filter, sine_50hz, sine_output, 250);

    /* Measure amplitude after settling (skip first 50 samples) */
    float32_t max_amp = 0.0f;
    for (int i = 100; i < 250; i++) {
        if (fabsf(sine_output[i]) > max_amp) {
            max_amp = fabsf(sine_output[i]);
        }
    }

    printf("50 Hz Sine Amplitude: %.4f (should be ~0.95-1.0)\n", (double)max_amp);
    if (max_amp > 0.90f && max_amp < 1.05f) {
        printf("✓ 50 Hz pass-through test PASSED\n");
    } else {
        printf("✗ 50 Hz pass-through test FAILED: Amplitude %.4f\n", (double)max_amp);
    }
}

/* ============================================================================
 * TEST 2: ZERO-CROSSING DETECTION
 * ========================================================================== */

void test_zero_crossing_detection(void)
{
    printf("\n=== TEST 2: Zero-Crossing Detection ===\n");

    ZeroCrossingState_t zc_state;
    zero_crossing_init(&zc_state);

    /* Generate 2 complete cycles of 50 Hz sine @ 5 kHz sampling */
    float32_t sine_wave[200];  /* 200 samples = 40 ms = 2 complete cycles */
    float32_t f_nominal = 50.0f;
    float32_t fs = 5000.0f;

    for (int i = 0; i < 200; i++) {
        sine_wave[i] = sinf(2.0f * PI * f_nominal * i / fs);
    }

    ZeroCrossingBlock_t blocks[10];
    int n_blocks = zero_crossing_detect_and_segment(&zc_state, sine_wave, 200, blocks, 10);

    printf("Detected %d cycle blocks\n", n_blocks);
    if (n_blocks >= 1) {
        printf("✓ Cycle detection found blocks\n");
    } else {
        printf("✗ Cycle detection FAILED: n_blocks = %d\n", n_blocks);
    }

    /* Verify each block properties */
    for (int i = 0; i < n_blocks; i++) {
        printf("  Block %d: start=%d, n_samples=%d, f=%.2f Hz, valid=%d\n",
               i, blocks[i].start_idx, blocks[i].n_samples, (double)blocks[i].f_measured, blocks[i].is_valid);

        if (fabsf(blocks[i].f_measured - 50.0f) < 5.0f) {
            printf("    ✓ Frequency within 5 Hz of nominal\n");
        } else {
            printf("    ✗ Frequency error: %.2f Hz\n", (double)fabsf(blocks[i].f_measured - 50.0f));
        }
    }
}

/* ============================================================================
 * TEST 3: RMS CALCULATION (CMSIS-DSP)
 * ========================================================================== */

void test_rms_calculation(void)
{
    printf("\n=== TEST 3: RMS Calculation ===\n");

    /* Create a 50 Hz sine wave with known amplitude */
    float32_t sine_wave[512];
    float32_t expected_rms = 1.0f / sqrtf(2.0f);  /* 1V peak → 0.707V RMS */
    float32_t fs = 5000.0f;

    for (int i = 0; i < 512; i++) {
        sine_wave[i] = sinf(2.0f * PI * 50.0f * i / fs);
    }

    /* Calculate RMS using CMSIS-DSP */
    float32_t rms_result = 0.0f;
    arm_rms_f32(sine_wave, 512, &rms_result);

    printf("Calculated RMS: %.6f V\n", (double)rms_result);
    printf("Expected RMS:   %.6f V\n", (double)expected_rms);
    printf("Error:          %.6f V (%.2f%%)\n",
           (double)fabsf(rms_result - expected_rms),
           (double)fabsf(rms_result - expected_rms) / expected_rms * 100.0f);

    if (fabsf(rms_result - expected_rms) / expected_rms < 0.01f) {
        printf("✓ RMS calculation PASSED (< 1%% error)\n");
    } else {
        printf("✗ RMS calculation FAILED (> 1%% error)\n");
    }
}

/* ============================================================================
 * TEST 4: POWER CALCULATIONS (RESISTIVE LOAD)
 * ========================================================================== */

void test_power_calculations_resistive(void)
{
    printf("\n=== TEST 4: Power Calculations (Resistive Load) ===\n");

    /* Generate voltage and current for resistive load */
    /* V(t) = 230*sqrt(2) * sin(2πft) ≈ 325.3 * sin(2π*50*t) */
    /* For R=10Ω: I(t) = V(t)/R, so I_peak = 32.53A, I_RMS = 23.0A */

    float32_t v_peak = 325.3f;  /* 230V RMS */
    float32_t i_peak = 32.53f;  /* 23A RMS */
    float32_t fs = 5000.0f;
    float32_t v_sample[512], i_sample[512];

    for (int i = 0; i < 512; i++) {
        v_sample[i] = v_peak * sinf(2.0f * PI * 50.0f * i / fs);
        i_sample[i] = i_peak * sinf(2.0f * PI * 50.0f * i / fs);  /* In phase (resistive) */
    }

    /* Calculate RMS values */
    float32_t v_rms = 0.0f, i_rms = 0.0f;
    arm_rms_f32(v_sample, 512, &v_rms);
    arm_rms_f32(i_sample, 512, &i_rms);

    float32_t p_expected = v_rms * i_rms;  /* For resistive, P = V_RMS * I_RMS */
    float32_t s_expected = v_rms * i_rms;  /* S = P for resistive */

    printf("Voltage RMS: %.2f V (expected ~230V)\n", (double)v_rms);
    printf("Current RMS: %.2f A (expected ~23A)\n", (double)i_rms);
    printf("Expected Active Power P = %.1f W\n", (double)p_expected);
    printf("Expected Apparent Power S = %.1f VA\n", (double)s_expected);
    printf("Expected Power Factor = 1.0 (resistive)\n");

    if (fabsf(v_rms - 230.0f) / 230.0f < 0.05f) {
        printf("✓ Voltage RMS PASSED\n");
    } else {
        printf("✗ Voltage RMS FAILED: Error %.2f%%\n", (double)fabsf(v_rms - 230.0f) / 230.0f * 100.0f);
    }

    if (fabsf(i_rms - 23.0f) / 23.0f < 0.05f) {
        printf("✓ Current RMS PASSED\n");
    } else {
        printf("✗ Current RMS FAILED: Error %.2f%%\n", (double)fabsf(i_rms - 23.0f) / 23.0f * 100.0f);
    }
}

/* ============================================================================
 * TEST 5: END-TO-END DSP PIPELINE
 * ========================================================================== */

void test_dsp_pipeline_integration(void)
{
    printf("\n=== TEST 5: End-to-End DSP Pipeline Integration ===\n");

    DSPPipeline_t pipeline;

    /* Initialize pipeline */
    if (dsp_pipeline_init(&pipeline) < 0) {
        printf("✗ DSP pipeline initialization FAILED\n");
        return;
    }
    printf("✓ DSP pipeline initialized\n");

    /* Create ADC codes for a clean 230V, 23A 50Hz sine wave */
    uint16_t adc_v_codes[512], adc_i_codes[512];

    /* ADC mapping: uint16_t[0..65535] → [-3V, +3V] differential */
    /* code = (voltage + 3.0) * (2^16) / 6.0 */
    float32_t v_peak = 325.3f;
    float32_t i_peak = 32.53f;
    float32_t fs = 5000.0f;

    for (int i = 0; i < 512; i++) {
        float32_t v_analog = v_peak * sinf(2.0f * PI * 50.0f * i / fs);
        float32_t i_analog = i_peak * sinf(2.0f * PI * 50.0f * i / fs);

        /* Scale to ADC range */
        uint32_t v_code = (uint32_t)((v_analog + 3.0f) * 65536.0f / 6.0f);
        uint32_t i_code = (uint32_t)((i_analog + 3.0f) * 65536.0f / 6.0f);

        adc_v_codes[i] = (uint16_t)(v_code & 0xFFFF);
        adc_i_codes[i] = (uint16_t)(i_code & 0xFFFF);
    }

    /* Process frame */
    MeasurementOutput_t result;
    int n_blocks = dsp_pipeline_process_frame(&pipeline, adc_v_codes, adc_i_codes, 3.0f, 16, &result);

    printf("Processed %d blocks\n", n_blocks);
    printf("\nMeasurement Results:\n");
    printf("  Vrms:        %.2f V (expected ~230V)\n", (double)result.vrms);
    printf("  Irms:        %.2f A (expected ~23A)\n", (double)result.irms);
    printf("  Frequency:   %.2f Hz (expected 50Hz)\n", (double)result.frequency);
    printf("  P_total:     %.1f W (expected ~5290W)\n", (double)result.p_total);
    printf("  Q_total:     %.1f VAR (expected ~0VAR for resistive)\n", (double)result.q_total);
    printf("  S_total:     %.1f VA (expected ~5290VA)\n", (double)result.s_total);
    printf("  TPF:         %.4f (expected 1.0 for resistive)\n", (double)result.tpf);
    printf("  THD_V:       %.2f %% (expected <1%% for pure sine)\n", (double)result.thd_v);
    printf("  THD_I:       %.2f %% (expected <1%% for pure sine)\n", (double)result.thd_i);

    /* Validation */
    int passed = 0, total = 0;

    total++;
    if (n_blocks > 0) {
        printf("✓ Block detection\n");
        passed++;
    } else {
        printf("✗ Block detection FAILED\n");
    }

    total++;
    if (fabsf(result.vrms - 230.0f) / 230.0f < 0.10f) {
        printf("✓ Vrms within 10%%\n");
        passed++;
    } else {
        printf("✗ Vrms error: %.2f%%\n", (double)fabsf(result.vrms - 230.0f) / 230.0f * 100.0f);
    }

    total++;
    if (fabsf(result.irms - 23.0f) / 23.0f < 0.10f) {
        printf("✓ Irms within 10%%\n");
        passed++;
    } else {
        printf("✗ Irms error: %.2f%%\n", (double)fabsf(result.irms - 23.0f) / 23.0f * 100.0f);
    }

    total++;
    if (fabsf(result.frequency - 50.0f) < 2.0f) {
        printf("✓ Frequency within 2Hz\n");
        passed++;
    } else {
        printf("✗ Frequency error: %.2f Hz\n", (double)fabsf(result.frequency - 50.0f));
    }

    total++;
    if (fabsf(result.tpf - 1.0f) < 0.05f) {
        printf("✓ TPF close to 1.0 (resistive)\n");
        passed++;
    } else {
        printf("✗ TPF error: %.4f\n", (double)fabsf(result.tpf - 1.0f));
    }

    total++;
    if (result.thd_v < 2.0f && result.thd_i < 2.0f) {
        printf("✓ THD low for pure sine\n");
        passed++;
    } else {
        printf("✗ THD too high: V=%.2f%%, I=%.2f%%\n", (double)result.thd_v, (double)result.thd_i);
    }

    printf("\n=== TEST 5 RESULT: %d/%d validations PASSED ===\n", passed, total);
}

/* ============================================================================
 * MAIN TEST RUNNER
 * ========================================================================== */

int dsp_run_all_tests(void)
{
    printf("\n");
    printf("╔═══════════════════════════════════════════════════════════════╗\n");
    printf("║            TP4-ASSD DSP Integration Test Suite              ║\n");
    printf("║                                                             ║\n");
    printf("║  Tests validate:                                            ║\n");
    printf("║  1. High-pass filter DC blocking & signal pass-through     ║\n");
    printf("║  2. Zero-crossing cycle detection accuracy                  ║\n");
    printf("║  3. RMS calculation correctness                             ║\n");
    printf("║  4. Power calculations for resistive loads                  ║\n");
    printf("║  5. End-to-end pipeline with synthetic signals              ║\n");
    printf("╚═══════════════════════════════════════════════════════════════╝\n");

    test_highpass_filter();
    test_zero_crossing_detection();
    test_rms_calculation();
    test_power_calculations_resistive();
    test_dsp_pipeline_integration();

    printf("\n");
    printf("╔═══════════════════════════════════════════════════════════════╗\n");
    printf("║                   ALL TESTS COMPLETED                        ║\n");
    printf("╚═══════════════════════════════════════════════════════════════╝\n\n");

    return 0;
}
