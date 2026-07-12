/**
 * @file dsp_pipeline.h
 * @brief DSP Pipeline Orchestration
 *
 * Orchestrates the complete signal processing pipeline:
 * Raw ADC samples → Filtered → Block-segmented → Harmonics extracted
 * → Power calculated → Results output
 *
 * This is the main entry point for DSP processing in the STM32 firmware.
 * All other DSP modules (filters, zero-crossing, goertzel, power_calc)
 * are coordinated here.
 *
 * References:
 * - TP4_ASSD.pdf: Complete signal processing block diagram
 * - power_analyzer/dsp/pipeline.py: Python reference
 * - dsp_config.h: Configuration parameters
 */

#ifndef DSP_PIPELINE_H
#define DSP_PIPELINE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"
#include "dsp_config.h"
#include "filters.h"
#include "zero_crossing.h"
#include "goertzel.h"
#include "power_calc.h"

/* ============================================================================
 * DSP PIPELINE STATE
 * ========================================================================== */

/**
 * @defgroup PipelineState DSP Pipeline State Management
 * @{
 */

/**
 * Complete DSP pipeline processor state
 *
 * Maintains all stateful objects (filters, FFT, zero-crossing detector)
 * and buffers required for processing frames of ADC samples.
 */
typedef struct {
    /* Filter states (one per channel) */
    HighPassFilterState_t filter_v;         /**< Voltage high-pass filter */
    HighPassFilterState_t filter_i;         /**< Current high-pass filter */

    /* FFT processor */
    FFTState_t fft;                         /**< FFT & harmonics extractor */

    /* Zero-crossing detector */
    ZeroCrossingState_t zc_detector;        /**< Zero-crossing detector state */

    /* Working buffers */
    float32_t v_filtered[N_SAMPLES];        /**< Filtered voltage buffer */
    float32_t i_filtered[N_SAMPLES];        /**< Filtered current buffer */

    /* Per-block measurement storage */
    MeasurementOutput_t block_measurements[50];  /**< Per-block results */
    uint16_t n_block_measurements;               /**< Number of measurements */

    /* Aggregated frame result */
    MeasurementOutput_t frame_result;       /**< Final averaged result */

    /* Statistics */
    uint32_t frame_count;                   /**< Total frames processed */
    uint32_t block_count;                   /**< Total blocks found */
    uint32_t error_count;                   /**< Frame processing errors */

    /* Initialization flag */
    uint8_t initialized;                    /**< Initialization status */
} DSPPipeline_t;

/**@}*/

/* ============================================================================
 * PIPELINE INITIALIZATION & MANAGEMENT
 * ========================================================================== */

/**
 * @brief Initialize DSP pipeline
 *
 * Sets up all filters, FFT processor, and detector states.
 * Must be called once during system startup before processing frames.
 *
 * @param[in,out] pipeline  Pointer to pipeline state structure
 * @return 0 on success, negative on error
 *
 * Example:
 * @code
 * DSPPipeline_t dsp;
 * int ret = dsp_pipeline_init(&dsp);
 * if (ret < 0) {
 *     printf("DSP init failed\n");
 * }
 * @endcode
 */
int dsp_pipeline_init(DSPPipeline_t *pipeline);

/**
 * @brief Reset pipeline state (clear history)
 *
 * Clears filter states, detector state, and measurement buffers.
 * Useful after mode changes or long idle periods.
 *
 * @param[in,out] pipeline  Pointer to pipeline state
 * @return void
 *
 * @note FFT tables are NOT reset (initialization is expensive)
 */
void dsp_pipeline_reset(DSPPipeline_t *pipeline);

/* ============================================================================
 * FRAME PROCESSING (MAIN ENTRY POINT)
 * ========================================================================== */

/**
 * @brief Process one frame of ADC samples
 *
 * Main entry point for DSP processing. Performs complete signal processing:
 * 1. Convert ADC codes (uint16_t) to physical units (float32_t)
 * 2. Apply high-pass filters to both channels
 * 3. Detect zero-crossings and segment into cycle blocks
 * 4. For each block:
 *    - Extract harmonics (FFT)
 *    - Calculate power metrics
 * 5. Average blocks to get frame result
 * 6. Output result via callback (or return structure)
 *
 * @param[in,out] pipeline      Pipeline state (updated after processing)
 * @param[in]  v_adc_codes     Voltage ADC codes (raw uint16_t, 512 samples)
 * @param[in]  i_adc_codes     Current ADC codes (raw uint16_t, 512 samples)
 * @param[in]  adc_vref        ADC reference voltage (V)
 * @param[in]  adc_bits        ADC resolution (bits)
 * @param[out] result          Processed measurement result
 * @return Number of blocks processed, negative on error
 *
 * Processing Steps:
 * - ADC code to voltage conversion: V = code * (2*vref / 2^bits)
 *   (factor of 2 for ±vref differential)
 * - RMS gain applied based on channel configuration
 * - Result contains all power metrics and harmonics
 *
 * @note
 * - Processing latency: ~200 ms per frame (may be optimized)
 * - Does NOT block (non-blocking call)
 * - Result is valid even if n_blocks = 0 (zero crossings not found)
 *
 * Example:
 * @code
 * uint16_t v_adc[512], i_adc[512];
 * MeasurementOutput_t result;
 * // ... fill ADC buffers from hardware ...
 * int n_blocks = dsp_pipeline_process_frame(
 *     &pipeline, v_adc, i_adc, 3.0f, 16, &result
 * );
 * if (n_blocks > 0) {
 *     printf("P=%.1f W, Q=%.1f VAR, PF=%.3f\n",
 *            result.p_total, result.q_total, result.tpf);
 * }
 * @endcode
 */
int dsp_pipeline_process_frame(
    DSPPipeline_t *pipeline,
    const uint16_t *v_adc_codes,
    const uint16_t *i_adc_codes,
    float32_t adc_vref,
    uint16_t adc_bits,
    MeasurementOutput_t *result
);

/* ============================================================================
 * PROCESSING STAGES (ADVANCED / DEBUGGING)
 * ========================================================================== */

/**
 * @brief Process just the filtering stage
 *
 * Applies high-pass filters to raw ADC-derived signals.
 * Useful for testing filter response independently.
 *
 * @param[in,out] pipeline      Pipeline state
 * @param[in]  v_adc_codes     Raw voltage ADC codes
 * @param[in]  i_adc_codes     Raw current ADC codes
 * @param[in]  adc_vref        ADC reference voltage
 * @param[in]  adc_bits        ADC resolution
 * @return void
 */
void dsp_pipeline_stage_filter(
    DSPPipeline_t *pipeline,
    const uint16_t *v_adc_codes,
    const uint16_t *i_adc_codes,
    float32_t adc_vref,
    uint16_t adc_bits
);

/**
 * @brief Process just the zero-crossing detection stage
 *
 * Detects cycles and creates blocks from filtered signal.
 * Requires: pipeline->v_filtered already populated (call stage_filter first)
 *
 * @param[in,out] pipeline  Pipeline state
 * @return Number of blocks detected
 */
int dsp_pipeline_stage_zero_crossing(DSPPipeline_t *pipeline);

/**
 * @brief Process just the harmonic extraction stage
 *
 * Extracts harmonics from cycle blocks using FFT.
 * Requires: Blocks already detected (call stage_zero_crossing first)
 *
 * @param[in,out] pipeline  Pipeline state
 * @return void
 */
void dsp_pipeline_stage_harmonics(DSPPipeline_t *pipeline);

/* ============================================================================
 * RESULT ACCESS & OUTPUT
 * ========================================================================== */

/**
 * @brief Get latest frame result
 *
 * Returns the most recently computed measurement result.
 *
 * @param[in]  pipeline  Pipeline state
 * @param[out] result    Copy of latest result
 * @return 0 on success, negative if no result available
 */
int dsp_pipeline_get_result(
    const DSPPipeline_t *pipeline,
    MeasurementOutput_t *result
);

/**
 * @brief Get processing statistics
 *
 * @param[in]  pipeline    Pipeline state
 * @param[out] frames      Total frames processed
 * @param[out] blocks      Total blocks detected
 * @param[out] errors      Processing errors
 * @return void
 */
void dsp_pipeline_get_stats(
    const DSPPipeline_t *pipeline,
    uint32_t *frames,
    uint32_t *blocks,
    uint32_t *errors
);

/**
 * @brief Reset processing statistics
 *
 * @param[in,out] pipeline  Pipeline state
 * @return void
 */
void dsp_pipeline_reset_stats(DSPPipeline_t *pipeline);

/* ============================================================================
 * CONFIGURATION & TUNING
 * ========================================================================== */

/**
 * @brief Change nominal fundamental frequency
 *
 * Used for grid frequency (50 Hz Europe, 60 Hz Americas).
 * Affects zero-crossing detection and harmonic extraction.
 *
 * @param[in,out] pipeline  Pipeline state
 * @param[in]  f_nominal    New nominal frequency (Hz)
 * @return 0 on success, negative if invalid
 *
 * Example:
 * @code
 * dsp_pipeline_set_frequency(&pipeline, 60.0f);  // US grid
 * @endcode
 */
int dsp_pipeline_set_frequency(DSPPipeline_t *pipeline, float32_t f_nominal);

/**
 * @brief Enable/disable specific processing stages
 *
 * Can selectively disable stages for testing or reduced latency.
 *
 * @param[in,out] pipeline  Pipeline state
 * @param[in]  enable_harmonics  Enable FFT harmonic extraction
 * @param[in]  enable_thd        Enable THD calculation
 * @return void
 */
void dsp_pipeline_enable_stages(
    DSPPipeline_t *pipeline,
    uint8_t enable_harmonics,
    uint8_t enable_thd
);

#ifdef __cplusplus
}
#endif

#endif /* DSP_PIPELINE_H */
