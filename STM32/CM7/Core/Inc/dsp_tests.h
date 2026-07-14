/**
 * @file dsp_tests.h
 * @brief DSP Test Suite Header
 *
 * Comprehensive testing of DSP modules with known signals.
 */

#ifndef DSP_TESTS_H
#define DSP_TESTS_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Run all DSP tests
 *
 * Tests validate:
 * - High-pass filter DC blocking and signal pass-through
 * - Zero-crossing cycle detection
 * - RMS calculations
 * - Power calculations
 * - End-to-end pipeline processing
 *
 * @return 0 on success
 */
int dsp_run_all_tests(void);

#ifdef __cplusplus
}
#endif

#endif /* DSP_TESTS_H */
