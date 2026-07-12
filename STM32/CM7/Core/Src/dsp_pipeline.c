/**
 * @file dsp_pipeline.c
 * @brief DSP Pipeline Implementation - Orchestrates Complete Signal Processing
 *
 * Implements the main DSP pipeline that coordinates:
 * 1. High-pass filtering (DC removal)
 * 2. Zero-crossing detection (cycle segmentation)
 * 3. Harmonic extraction (FFT-based)
 * 4. Power calculations
 * 5. Results aggregation
 *
 * Reference:
 * - TP4_ASSD.pdf: Signal processing block diagram (flowchart, page 2)
 * - power_analyzer/dsp/pipeline.py: Python reference
 */

#include "dsp_pipeline.h"
#include <math.h>
#include <string.h>

/* ============================================================================
 * HELPER FUNCTIONS - ADC CODE CONVERSION
 * ========================================================================== */

/**
 * @brief Convert ADC code (raw uint16) to physical voltage
 *
 * Mapping: code ∈ [0, 2^bits) → voltage ∈ [−vref, +vref]
 *
 * For differential ADC with reference ±3V:
 * voltage = (code / 2^bits) * 2*vref - vref
 *         = code * (2*vref / 2^bits) - vref
 */
static float32_t adc_code_to_voltage(
    uint16_t code,
    float32_t vref,
    uint16_t bits
)
{
    float32_t full_scale = (float32_t)(1U << bits);  /* 2^bits */
    float32_t normalized = (float32_t)code / full_scale;
    return normalized * 2.0f * vref - vref;
}

/**
 * @brief Convert entire ADC code buffer to float32 voltage buffer
 */
static void adc_codes_to_voltages(
    const uint16_t *adc_codes,
    uint16_t n_samples,
    float32_t *voltages,
    float32_t vref,
    uint16_t bits
)
{
    if (!adc_codes || !voltages) {
        return;
    }

    for (uint16_t i = 0; i < n_samples; i++) {
        voltages[i] = adc_code_to_voltage(adc_codes[i], vref, bits);
    }
}

/* ============================================================================
 * PIPELINE INITIALIZATION
 * ========================================================================== */

int dsp_pipeline_init(DSPPipeline_t *pipeline)
{
    if (!pipeline) {
        return -1;
    }

    /* Initialize all stateful components */

    /* 1. High-pass filters */
    filters_highpass_init(&pipeline->filter_v);
    filters_highpass_init(&pipeline->filter_i);

    /* 2. FFT processor */
    goertzel_init(&pipeline->fft);

    /* 3. Zero-crossing detector */
    zero_crossing_init(&pipeline->zc_detector);

    /* 4. Clear buffers */
    memset(pipeline->v_filtered, 0, sizeof(pipeline->v_filtered));
    memset(pipeline->i_filtered, 0, sizeof(pipeline->i_filtered));
    memset(pipeline->block_measurements, 0, sizeof(pipeline->block_measurements));
    memset(&pipeline->frame_result, 0, sizeof(pipeline->frame_result));

    /* 5. Initialize statistics */
    pipeline->frame_count = 0;
    pipeline->block_count = 0;
    pipeline->error_count = 0;
    pipeline->n_block_measurements = 0;

    pipeline->initialized = 1;

    return 0;
}

void dsp_pipeline_reset(DSPPipeline_t *pipeline)
{
    if (!pipeline) {
        return;
    }

    /* Reset filter states (clears history) */
    filters_highpass_reset(&pipeline->filter_v);
    filters_highpass_reset(&pipeline->filter_i);

    /* Reset detector state */
    zero_crossing_reset(&pipeline->zc_detector);

    /* Clear measurement buffers */
    memset(pipeline->block_measurements, 0, sizeof(pipeline->block_measurements));
    pipeline->n_block_measurements = 0;
    memset(&pipeline->frame_result, 0, sizeof(pipeline->frame_result));

    /* Do NOT reset FFT (initialization is expensive, tables are constant) */
}

/* ============================================================================
 * PROCESSING STAGES
 * ========================================================================== */

void dsp_pipeline_stage_filter(
    DSPPipeline_t *pipeline,
    const uint16_t *v_adc_codes,
    const uint16_t *i_adc_codes,
    float32_t adc_vref,
    uint16_t adc_bits
)
{
    if (!pipeline || !v_adc_codes || !i_adc_codes) {
        return;
    }

    /* Step 1: Convert ADC codes to float32 voltages */
    float32_t v_float[N_SAMPLES], i_float[N_SAMPLES];

    adc_codes_to_voltages(v_adc_codes, N_SAMPLES, v_float, adc_vref, adc_bits);
    adc_codes_to_voltages(i_adc_codes, N_SAMPLES, i_float, adc_vref, adc_bits);

    /* Step 2: Apply high-pass filters (DC removal) */
    filters_highpass_apply_dual(
        &pipeline->filter_v,
        &pipeline->filter_i,
        v_float, i_float,
        pipeline->v_filtered, pipeline->i_filtered,
        N_SAMPLES
    );
}

int dsp_pipeline_stage_zero_crossing(DSPPipeline_t *pipeline)
{
    if (!pipeline) {
        return -1;
    }

    /* Detect zero-crossings and segment into blocks */
    ZeroCrossingBlock_t blocks[50];

    int n_blocks = zero_crossing_detect_and_segment(
        &pipeline->zc_detector,
        pipeline->v_filtered,
        N_SAMPLES,
        blocks,
        50
    );

    return n_blocks;
}

void dsp_pipeline_stage_harmonics(DSPPipeline_t *pipeline)
{
    /* This stage is integrated into process_frame */
    (void)pipeline;  /* Unused in this stub */
}

/* ============================================================================
 * MAIN FRAME PROCESSING
 * ========================================================================== */

int dsp_pipeline_process_frame(
    DSPPipeline_t *pipeline,
    const uint16_t *v_adc_codes,
    const uint16_t *i_adc_codes,
    float32_t adc_vref,
    uint16_t adc_bits,
    MeasurementOutput_t *result
)
{
    if (!pipeline || !v_adc_codes || !i_adc_codes || !result) {
        return -1;
    }

    if (!pipeline->initialized) {
        if (dsp_pipeline_init(pipeline) < 0) {
            return -1;
        }
    }

    /* ===== STAGE 1: FILTERING (DC REMOVAL) ===== */
    dsp_pipeline_stage_filter(
        pipeline, v_adc_codes, i_adc_codes, adc_vref, adc_bits
    );

    /* ===== STAGE 2: ZERO-CROSSING DETECTION & SEGMENTATION ===== */
    ZeroCrossingBlock_t blocks[50];
    int n_blocks = zero_crossing_detect_and_segment(
        &pipeline->zc_detector,
        pipeline->v_filtered,
        N_SAMPLES,
        blocks,
        50
    );

    if (n_blocks <= 0) {
        /* No valid blocks found - return empty result */
        memset(result, 0, sizeof(MeasurementOutput_t));
        pipeline->frame_count++;
        pipeline->error_count++;
        return 0;
    }

    /* ===== STAGE 3: PER-BLOCK ANALYSIS ===== */
    pipeline->n_block_measurements = 0;

    for (int b = 0; b < n_blocks && b < 50; b++) {
        ZeroCrossingBlock_t *blk = &blocks[b];

        if (!blk->is_valid || blk->n_samples == 0) {
            continue;
        }

        /* Extract samples for this cycle block */
        /* Note: We process blocks in-place from filtered buffer */

        /* Allocate temporary cycle buffers */
        float32_t v_cycle[256], i_cycle[256];

        if (blk->n_samples > 256) {
            /* Limit block size for safety */
            continue;
        }

        /* Copy cycle from filtered buffers */
        for (uint16_t i = 0; i < blk->n_samples; i++) {
            v_cycle[i] = pipeline->v_filtered[blk->start_idx + i];
            i_cycle[i] = pipeline->i_filtered[blk->start_idx + i];
        }

        /* Analyze this cycle block */
        MeasurementOutput_t *blk_result =
            &pipeline->block_measurements[pipeline->n_block_measurements];

        power_calc_analyze_block(
            v_cycle, i_cycle,
            blk->n_samples,
            blk->f_measured,
            &pipeline->fft,
            blk_result
        );

        pipeline->n_block_measurements++;
    }

    /* ===== STAGE 4: AVERAGING ===== */
    if (pipeline->n_block_measurements > 0) {
        power_calc_average_blocks(
            pipeline->block_measurements,
            pipeline->n_block_measurements,
            &pipeline->frame_result
        );

        /* Copy to output */
        memcpy(result, &pipeline->frame_result, sizeof(MeasurementOutput_t));
    } else {
        memset(result, 0, sizeof(MeasurementOutput_t));
    }

    /* ===== UPDATE STATISTICS ===== */
    pipeline->frame_count++;
    pipeline->block_count += n_blocks;

    return n_blocks;
}

/* ============================================================================
 * RESULT ACCESS
 * ========================================================================== */

int dsp_pipeline_get_result(
    const DSPPipeline_t *pipeline,
    MeasurementOutput_t *result
)
{
    if (!pipeline || !result) {
        return -1;
    }

    if (pipeline->frame_result.n_blocks == 0) {
        return -1;  /* No valid result yet */
    }

    memcpy(result, &pipeline->frame_result, sizeof(MeasurementOutput_t));
    return 0;
}

void dsp_pipeline_get_stats(
    const DSPPipeline_t *pipeline,
    uint32_t *frames,
    uint32_t *blocks,
    uint32_t *errors
)
{
    if (!pipeline) {
        return;
    }

    if (frames) *frames = pipeline->frame_count;
    if (blocks) *blocks = pipeline->block_count;
    if (errors) *errors = pipeline->error_count;
}

void dsp_pipeline_reset_stats(DSPPipeline_t *pipeline)
{
    if (!pipeline) {
        return;
    }

    pipeline->frame_count = 0;
    pipeline->block_count = 0;
    pipeline->error_count = 0;
}

/* ============================================================================
 * CONFIGURATION
 * ========================================================================== */

int dsp_pipeline_set_frequency(DSPPipeline_t *pipeline, float32_t f_nominal)
{
    if (!pipeline || f_nominal < 40.0f || f_nominal > 70.0f) {
        return -1;
    }

    /* Frequency is used in zero-crossing detection */
    /* Currently embedded in dsp_config.h defines, but can be extended */
    /* For now, just validate */

    return 0;
}

void dsp_pipeline_enable_stages(
    DSPPipeline_t *pipeline,
    uint8_t enable_harmonics,
    uint8_t enable_thd
)
{
    if (!pipeline) {
        return;
    }

    /* These flags could be stored in pipeline and checked during processing */
    /* Currently not implemented - all stages always run */
    (void)enable_harmonics;
    (void)enable_thd;
}

/* ============================================================================
 * DEBUG & DIAGNOSTICS
 * ========================================================================== */

#if DEBUG_DSP

void dsp_pipeline_print_state(const DSPPipeline_t *pipeline)
{
    if (!pipeline) {
        return;
    }

    printf("=== DSP Pipeline State ===\n");
    printf("Initialized: %d\n", pipeline->initialized);
    printf("Frames: %lu\n", pipeline->frame_count);
    printf("Blocks: %lu\n", pipeline->block_count);
    printf("Errors: %lu\n", pipeline->error_count);
    printf("Current blocks measured: %u\n", pipeline->n_block_measurements);
}

#endif /* DEBUG_DSP */
