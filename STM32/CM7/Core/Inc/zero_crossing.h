/**
 * @file zero_crossing.h
 * @brief Zero-Crossing Detection for Cycle Block Segmentation
 *
 * Detects positive zero-crossings in voltage signal to segment data into
 * complete AC cycles. Essential for synchronizing power calculations to
 * the mains fundamental frequency.
 *
 * References:
 * - power_analyzer/dsp/zero_crossing.py: Python reference implementation
 * - TP4_ASSD.pdf: Block diagram stage 4 (Detección de Cruces por Cero)
 */

#ifndef ZERO_CROSSING_H
#define ZERO_CROSSING_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include "arm_math.h"
#include "dsp_config.h"

/* ============================================================================
 * ZERO-CROSSING DETECTION DATA STRUCTURES
 * ========================================================================== */

/**
 * @defgroup ZeroCrossingStructures Zero-Crossing Detection Structures
 * @{
 */

/**
 * Result of detecting a single zero-crossing
 */
typedef struct {
    uint16_t sample_idx;        /**< Sample index where crossing detected */
    float32_t interp_idx;       /**< Interpolated index (fractional) */
    float32_t interpolated_value; /**< Interpolated zero value */
} ZeroCrossing_t;

/**
 * Represents a complete AC cycle block (from one ZC to next)
 */
typedef struct {
    uint16_t start_idx;         /**< Sample index of start of cycle */
    uint16_t end_idx;           /**< Sample index of end of cycle */
    uint16_t n_samples;         /**< Number of samples in this cycle */
    float32_t f_measured;       /**< Measured fundamental frequency (Hz) */
    uint8_t is_valid;           /**< Flag: block contains complete cycle */
} ZeroCrossingBlock_t;

/**
 * Zero-crossing detector state (maintains history for settling)
 */
typedef struct {
    uint16_t n_crossings_detected;  /**< Total crossings found in frame */
    uint16_t n_blocks_found;        /**< Total blocks extracted */
    float32_t prev_sample;          /**< Previous sample value (for ZC detection) */
    uint8_t state_initialized;      /**< Flag: detector has previous sample */
} ZeroCrossingState_t;

/**@}*/

/* ============================================================================
 * INITIALIZATION
 * ========================================================================== */

/**
 * @brief Initialize zero-crossing detector
 *
 * Sets up detector state for the first frame. After this,
 * detector state is maintained across frames.
 *
 * @param[in,out] state Pointer to detector state
 * @return void
 */
void zero_crossing_init(ZeroCrossingState_t *state);

/* ============================================================================
 * ZERO-CROSSING DETECTION
 * ========================================================================== */

/**
 * @brief Find positive zero-crossings in a signal
 *
 * Detects sample indices where signal crosses zero from negative to positive,
 * with linear interpolation for sub-sample accuracy.
 *
 * @param[in]  signal          Filtered input signal (voltage)
 * @param[in]  n_samples       Number of samples in signal
 * @param[out] crossings       Output array of detected crossings
 * @param[in]  max_crossings   Maximum crossings to detect
 * @return Number of zero-crossings found (≤ max_crossings)
 *
 * @note
 * - Requires at least 2 samples to find first crossing
 * - Linear interpolation assumes linear signal between samples
 * - Requires high-pass filtered input (DC removed)
 *
 * Example:
 * @code
 * float32_t v_filtered[512];
 * ZeroCrossing_t crossings[100];  // Expect ~10 crossings per frame
 * int n_zc = zero_crossing_find_positive(v_filtered, 512, crossings, 100);
 * @endcode
 */
int zero_crossing_find_positive(
    const float32_t *signal,
    uint16_t n_samples,
    ZeroCrossing_t *crossings,
    uint16_t max_crossings
);

/* ============================================================================
 * BLOCK SEGMENTATION
 * ========================================================================== */

/**
 * @brief Segment signal into complete AC cycle blocks
 *
 * Takes array of zero-crossings and creates blocks representing
 * complete cycles. Validates block completeness and calculates
 * measured frequency for each block.
 *
 * @param[in]  crossings       Array of detected zero-crossings
 * @param[in]  n_crossings     Number of crossings
 * @param[out] blocks          Output blocks array
 * @param[in]  max_blocks      Maximum blocks to create
 * @param[in]  f_nominal       Expected nominal frequency (Hz)
 * @param[in]  settle_count    Number of crossings to skip (settling)
 * @return Number of complete blocks created
 *
 * @note
 * - Requires at least 2 crossings to make 1 block
 * - Skips first 'settle_count' crossings (default 5)
 * - Calculates frequency from crossing interval
 * - Validates frequency within F0_MIN..F0_MAX band
 *
 * Example:
 * @code
 * ZeroCrossingBlock_t blocks[50];
 * int n_blocks = zero_crossing_make_blocks(
 *     crossings, n_zc, blocks, 50, F0_NOMINAL, SETTLE_CROSSINGS
 * );
 * @endcode
 */
int zero_crossing_make_blocks(
    const ZeroCrossing_t *crossings,
    uint16_t n_crossings,
    ZeroCrossingBlock_t *blocks,
    uint16_t max_blocks,
    float32_t f_nominal,
    uint16_t settle_count
);

/* ============================================================================
 * CONVENIENCE FUNCTIONS
 * ========================================================================== */

/**
 * @brief Detect zero-crossings and segment into blocks (combined)
 *
 * Single-call function that does both zero-crossing detection and
 * block segmentation. Useful for simple cases.
 *
 * @param[in,out] state        Detector state (updated after call)
 * @param[in]  signal          Filtered voltage signal
 * @param[in]  n_samples       Signal length
 * @param[out] blocks          Output blocks array
 * @param[in]  max_blocks      Maximum blocks
 * @return Number of blocks created
 */
int zero_crossing_detect_and_segment(
    ZeroCrossingState_t *state,
    const float32_t *signal,
    uint16_t n_samples,
    ZeroCrossingBlock_t *blocks,
    uint16_t max_blocks
);

/* ============================================================================
 * STATE MANAGEMENT
 * ========================================================================== */

/**
 * @brief Reset detector state (clear history)
 *
 * Clears previous sample and flags. Useful after:
 * - Changing operating mode
 * - Long idle periods
 * - Stopping/restarting measurement
 *
 * @param[in,out] state Detector state
 * @return void
 *
 * @warning After reset, first block may be incomplete due to missing
 *          previous sample. This is normal.
 */
void zero_crossing_reset(ZeroCrossingState_t *state);

/* ============================================================================
 * FREQUENCY ESTIMATION
 * ========================================================================== */

/**
 * @brief Estimate fundamental frequency from zero-crossing interval
 *
 * Calculates frequency based on time between consecutive zero-crossings.
 * For a pure 50 Hz sine, should detect ~100 crossings/second (positive only).
 *
 * @param[in] zc1           First zero-crossing
 * @param[in] zc2           Second zero-crossing (next positive ZC)
 * @param[in] sample_rate   ADC sample rate (Hz)
 * @return Measured frequency (Hz)
 *
 * @note
 * - For 50 Hz at 5 kHz sample rate: 50 crossings/sec → ~100 sample interval
 * - Assumes one complete cycle between positive ZCs
 * - High-pass filter removes DC offset, ensuring proper ZC detection
 */
float32_t zero_crossing_estimate_frequency(
    const ZeroCrossing_t *zc1,
    const ZeroCrossing_t *zc2,
    float32_t sample_rate
);

#ifdef __cplusplus
}
#endif

#endif /* ZERO_CROSSING_H */
