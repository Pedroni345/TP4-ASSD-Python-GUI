/**
 * @file zero_crossing.c
 * @brief Zero-Crossing Detection Implementation
 *
 * Implements cycle block segmentation based on positive zero-crossings
 * in the voltage signal. Uses linear interpolation for sub-sample accuracy.
 *
 * Theory:
 * -------
 * For a filtered sinusoidal signal x[n]:
 * - Zero-crossing: x[n-1] < 0 and x[n] > 0 (positive ZC)
 * - Interpolated index: idx + (0 - x[n-1]) / (x[n] - x[n-1])
 *
 * Reference:
 * - power_analyzer/dsp/zero_crossing.py: find_positive_crossings() [lines 1-40]
 * - TP4_ASSD.pdf: Signal segmentation specification
 */

#include "zero_crossing.h"
#include <math.h>
#include <string.h>

/* ============================================================================
 * INITIALIZATION
 * ========================================================================== */

void zero_crossing_init(ZeroCrossingState_t *state)
{
    if (!state) {
        return;
    }

    state->n_crossings_detected = 0;
    state->n_blocks_found = 0;
    state->prev_sample = 0.0f;
    state->state_initialized = 0;
}

/* ============================================================================
 * ZERO-CROSSING DETECTION (WITH LINEAR INTERPOLATION)
 * ========================================================================== */

int zero_crossing_find_positive(
    const float32_t *signal,
    uint16_t n_samples,
    ZeroCrossing_t *crossings,
    uint16_t max_crossings
)
{
    if (!signal || !crossings || n_samples < 2 || max_crossings == 0) {
        return 0;
    }

    int n_found = 0;
    float32_t prev = signal[0];

    for (uint16_t i = 1; i < n_samples && n_found < max_crossings; i++) {
        float32_t curr = signal[i];

        /* Detect positive zero-crossing: prev < 0 and curr > 0 */
        if (prev < 0.0f && curr > 0.0f) {
            /* Linear interpolation for sub-sample accuracy:
             * Solve: x(t) = prev + t*(curr - prev) = 0
             * t = -prev / (curr - prev)
             * True index = i - 1 + t
             */
            float32_t delta = curr - prev;
            float32_t t = -prev / delta;  /* t in [0, 1] */
            float32_t interp_idx = (float32_t)(i - 1) + t;

            crossings[n_found].sample_idx = i;
            crossings[n_found].interp_idx = interp_idx;
            crossings[n_found].interpolated_value = 0.0f;  /* By definition */

            n_found++;
        }

        prev = curr;
    }

    return n_found;
}

/* ============================================================================
 * BLOCK SEGMENTATION (CYCLE GROUPING)
 * ========================================================================== */

int zero_crossing_make_blocks(
    const ZeroCrossing_t *crossings,
    uint16_t n_crossings,
    ZeroCrossingBlock_t *blocks,
    uint16_t max_blocks,
    float32_t f_nominal,
    uint16_t settle_count
)
{
    if (!crossings || !blocks || n_crossings < 2 || max_blocks == 0) {
        return 0;
    }

    int n_blocks = 0;

    /* Skip settle_count crossings (default 5) to allow filter to stabilize */
    uint16_t start_idx = (settle_count < n_crossings) ? settle_count : n_crossings - 1;

    /**
     * Create blocks between consecutive zero-crossings
     * Each block spans from one positive ZC to the next
     * This represents one complete AC cycle
     */
    for (uint16_t i = start_idx; i < n_crossings - 1 && n_blocks < max_blocks; i++) {
        ZeroCrossingBlock_t *blk = &blocks[n_blocks];

        blk->start_idx = crossings[i].sample_idx;
        blk->end_idx = crossings[i + 1].sample_idx;
        blk->n_samples = blk->end_idx - blk->start_idx;

        /* Calculate measured frequency from zero-crossing interval
         * For one complete cycle: period = 2 * (time between ZCs)
         * Frequency = 1 / period = sample_rate / (2 * n_samples)
         * (factor of 2 because ZC detection gives crossings per cycle)
         */
        blk->f_measured = zero_crossing_estimate_frequency(
            &crossings[i],
            &crossings[i + 1],
            (float32_t)FS_DIGITAL
        );

        /**
         * Validate block:
         * - Frequency within expected range (F0_MIN to F0_MAX)
         * - Block has samples
         */
        if (blk->n_samples > 0 &&
            blk->f_measured >= F0_MIN &&
            blk->f_measured <= F0_MAX) {
            blk->is_valid = 1;
            n_blocks++;
        } else {
            blk->is_valid = 0;
        }
    }

    return n_blocks;
}

/* ============================================================================
 * CONVENIENCE FUNCTIONS
 * ========================================================================== */

int zero_crossing_detect_and_segment(
    ZeroCrossingState_t *state,
    const float32_t *signal,
    uint16_t n_samples,
    ZeroCrossingBlock_t *blocks,
    uint16_t max_blocks
)
{
    if (!state || !signal || !blocks || n_samples == 0 || max_blocks == 0) {
        return 0;
    }

    /**
     * Temporary storage for crossings
     * Upper bound: ~10-15 crossings per 512 samples @ 5 kHz (50 Hz signal)
     */
    ZeroCrossing_t crossings[20];

    /* Detect zero-crossings in current frame */
    int n_zc = zero_crossing_find_positive(signal, n_samples, crossings, 20);

    if (n_zc < 2) {
        return 0;  /* Need at least 2 ZCs to make 1 block */
    }

    /* Segment into blocks */
    int n_blocks = zero_crossing_make_blocks(
        crossings,
        n_zc,
        blocks,
        max_blocks,
        F0_NOMINAL,
        SETTLE_CROSSINGS
    );

    /* Update state */
    state->n_crossings_detected += n_zc;
    state->n_blocks_found += n_blocks;
    if (n_zc > 0) {
        state->prev_sample = signal[n_samples - 1];
        state->state_initialized = 1;
    }

    return n_blocks;
}

/* ============================================================================
 * STATE MANAGEMENT
 * ========================================================================== */

void zero_crossing_reset(ZeroCrossingState_t *state)
{
    if (!state) {
        return;
    }

    state->prev_sample = 0.0f;
    state->state_initialized = 0;
}

/* ============================================================================
 * FREQUENCY ESTIMATION
 * ========================================================================== */

float32_t zero_crossing_estimate_frequency(
    const ZeroCrossing_t *zc1,
    const ZeroCrossing_t *zc2,
    float32_t sample_rate
)
{
    if (!zc1 || !zc2 || sample_rate <= 0.0f) {
        return F0_NOMINAL;  /* Fallback */
    }

    /**
     * Interval between consecutive positive zero-crossings represents
     * one complete cycle of the AC waveform.
     *
     * Period = (sample_interval / sample_rate) seconds
     * Frequency = sample_rate / sample_interval
     *
     * Using interpolated indices for sub-sample accuracy:
     * interval = zc2->interp_idx - zc1->interp_idx
     */
    float32_t sample_interval = zc2->interp_idx - zc1->interp_idx;

    if (sample_interval <= 0.0f) {
        return F0_NOMINAL;  /* Invalid interval */
    }

    float32_t frequency = sample_rate / sample_interval;

    /**
     * Sanity check: reject frequency estimates way outside expected range
     * (This can happen if ZC detection is noisy)
     */
    if (frequency < F0_MIN || frequency > F0_MAX) {
        return F0_NOMINAL;
    }

    return frequency;
}

/* ============================================================================
 * TESTING & DEBUG UTILITIES
 * ========================================================================== */

#if DEBUG_ZERO_CROSSING

/**
 * @brief Print detected zero-crossings (for debugging)
 */
void zero_crossing_print_detections(
    const ZeroCrossing_t *crossings,
    int n_crossings
)
{
    if (!crossings || n_crossings == 0) {
        printf("No zero-crossings detected\n");
        return;
    }

    printf("Detected %d zero-crossings:\n", n_crossings);
    for (int i = 0; i < n_crossings; i++) {
        printf("  [%2d] idx=%4u, interp=%.2f\n",
               i,
               crossings[i].sample_idx,
               crossings[i].interp_idx);
    }
}

/**
 * @brief Print segmented blocks (for debugging)
 */
void zero_crossing_print_blocks(
    const ZeroCrossingBlock_t *blocks,
    int n_blocks
)
{
    if (!blocks || n_blocks == 0) {
        printf("No blocks created\n");
        return;
    }

    printf("Segmented into %d blocks:\n", n_blocks);
    for (int i = 0; i < n_blocks; i++) {
        printf("  [%2d] idx %4u-%4u (%3u samps), f=%.2f Hz, valid=%d\n",
               i,
               blocks[i].start_idx,
               blocks[i].end_idx,
               blocks[i].n_samples,
               (double)blocks[i].f_measured,
               blocks[i].is_valid);
    }
}

#endif /* DEBUG_ZERO_CROSSING */
