/**
 * @file goertzel.c
 * @brief Harmonic Extraction Implementation (CMSIS Real FFT)
 *
 * Extracts voltage and current phasors using hardware-accelerated
 * Real FFT from CMSIS-DSP library.
 *
 * Theory:
 * -------
 * 1. Hann Window: Reduces spectral leakage in FFT
 *    w[n] = 0.5 * (1 - cos(2π*n/(N-1))) for n=0..N-1
 *
 * 2. Real FFT: x[k] ↔ X[k], where X[k] = Re[k] + j*Im[k]
 *    Bin k corresponds to frequency: f_k = k * (fs / N)
 *
 * 3. Harmonic Extraction:
 *    For each harmonic order m (1, 2, 3, ..., 23):
 *    - Frequency: f_m = m * f_fundamental
 *    - Bin index: k_m = f_m * N / fs
 *    - Linear interpolation between nearest bins for sub-bin accuracy
 *    - Magnitude: |X[k_m]| (normalized by window scaling)
 *    - Phase: atan2(Im[k_m], Re[k_m])
 *
 * Reference:
 * - CMSIS-DSP: arm_rfft_fast_f32() for Real FFT
 * - Python reference: goertzel.py + filters.py for window generation
 */

#include "goertzel.h"
#include <math.h>
#include <string.h>

/* ============================================================================
 * CONSTANTS & HELPER MACROS
 * ========================================================================== */

/**
 * Coherent gain correction factor for Hann window
 * Accounts for magnitude reduction due to windowing
 * For Hann window: compensation = 2.0 / (number of samples * average window value)
 */
#define HANN_COHERENT_GAIN_CORRECTION (2.0f)

/**
 * RMS conversion: FFT gives peak magnitude, but power calculations need RMS
 * For sinusoid: RMS = peak / sqrt(2)
 * Included in harmonic normalization
 */
#define PEAK_TO_RMS  (1.0f / 1.41421356f)  /* 1/sqrt(2) */

/* ============================================================================
 * HANN WINDOW GENERATION
 * ========================================================================== */

/**
 * @brief Generate Hann window coefficients
 *
 * Hann window: w[n] = 0.5 * (1 - cos(2π*n/(N-1)))
 */
static void generate_hann_window(float32_t *window, uint16_t N)
{
    if (!window || N == 0) {
        return;
    }

    const float32_t pi = 3.14159265f;
    const float32_t scale = 2.0f * pi / (float32_t)(N - 1);

    for (uint16_t n = 0; n < N; n++) {
        float32_t arg = scale * (float32_t)n;
        window[n] = 0.5f * (1.0f - cosf(arg));
    }
}

/**
 * @brief Apply Hann window to signal
 */
static void apply_hann_window(
    float32_t *signal,
    const float32_t *window,
    uint16_t N
)
{
    if (!signal || !window || N == 0) {
        return;
    }

    for (uint16_t n = 0; n < N; n++) {
        signal[n] *= window[n];
    }
}

/* ============================================================================
 * FFT INITIALIZATION
 * ========================================================================== */

void goertzel_init(FFTState_t *fft_state)
{
    if (!fft_state) {
        return;
    }

    /* Initialize CMSIS Real FFT instance for FFT_SIZE samples */
    arm_rfft_fast_init_f32(&fft_state->fft_instance, FFT_SIZE);

    /* Generate Hann window coefficients */
    generate_hann_window(fft_state->window_coeffs, FFT_SIZE);

    fft_state->initialized = 1;
}

/* ============================================================================
 * HARMONIC EXTRACTION
 * ========================================================================== */

void goertzel_extract_harmonics(
    FFTState_t *fft_state,
    const float32_t *signal,
    uint16_t n_samples,
    float32_t f_measured,
    HarmonicSet_t *harmonics
)
{
    if (!fft_state || !signal || !harmonics || n_samples == 0) {
        return;
    }

    if (!fft_state->initialized) {
        goertzel_init(fft_state);
    }

    /* Prepare working buffer for FFT (we'll modify signal content)
     * In practice, we create a zero-padded copy to avoid overwriting input
     */
    float32_t time_domain[FFT_SIZE];

    /* Copy input signal to working buffer */
    for (uint16_t i = 0; i < n_samples && i < FFT_SIZE; i++) {
        time_domain[i] = signal[i];
    }

    /* Zero-pad if input is shorter than FFT_SIZE */
    for (uint16_t i = n_samples; i < FFT_SIZE; i++) {
        time_domain[i] = 0.0f;
    }

    /* Apply Hann window to reduce spectral leakage */
    apply_hann_window(time_domain, fft_state->window_coeffs, FFT_SIZE);

    /* Compute Real FFT
     * Output: fft_output[0..FFT_SIZE-1] in interleaved format:
     * [DC_real, nyquist, bin1_real, bin1_imag, bin2_real, bin2_imag, ...]
     */
    arm_rfft_fast_f32(&fft_state->fft_instance, time_domain, fft_state->fft_output, 0);

    /* Store fundamental frequency for reference */
    harmonics->f_fundamental = f_measured;
    harmonics->n_harmonics = MAX_HARMONIC + 1;

    /**
     * Extract harmonics
     * For each harmonic order m (1..MAX_HARMONIC):
     * 1. Calculate frequency: f_m = m * f_measured
     * 2. Calculate bin index: bin_m = f_m * FFT_SIZE / FS_DIGITAL
     * 3. Interpolate between adjacent bins if not integer
     * 4. Calculate magnitude and phase
     * 5. Normalize magnitude (window + peak-to-RMS conversion)
     */

    for (uint16_t m = 1; m <= MAX_HARMONIC; m++) {
        /* Calculate target frequency for this harmonic */
        float32_t f_harmonic = m * f_measured;

        /* Calculate bin index (may be fractional) */
        float32_t bin_float = f_harmonic * (float32_t)FFT_SIZE / (float32_t)FS_DIGITAL;

        /* Extract integer and fractional parts */
        uint16_t bin_low = (uint16_t)bin_float;
        float32_t frac = bin_float - (float32_t)bin_low;
        uint16_t bin_high = (bin_low < (FFT_SIZE / 2 - 1)) ? bin_low + 1 : bin_low;

        /**
         * Extract complex values from FFT output
         * CMSIS Real FFT output format:
         * [0] = DC real
         * [1] = Nyquist real
         * [2k] = bin k real component
         * [2k+1] = bin k imaginary component
         */

        float32_t real_low = 0.0f, imag_low = 0.0f;
        float32_t real_high = 0.0f, imag_high = 0.0f;

        if (bin_low > 0 && bin_low < FFT_SIZE / 2) {
            real_low = fft_state->fft_output[2 * bin_low];
            imag_low = fft_state->fft_output[2 * bin_low + 1];
        }

        if (bin_high > 0 && bin_high < FFT_SIZE / 2 && bin_high != bin_low) {
            real_high = fft_state->fft_output[2 * bin_high];
            imag_high = fft_state->fft_output[2 * bin_high + 1];
        } else {
            real_high = real_low;
            imag_high = imag_low;
        }

        /* Linear interpolation for sub-bin accuracy */
        float32_t real = real_low + frac * (real_high - real_low);
        float32_t imag = imag_low + frac * (imag_high - imag_low);

        /* Store phasor in rectangular form */
        harmonics->harmonics[m].phasor.real = real;
        harmonics->harmonics[m].phasor.imag = imag;

        /* Calculate magnitude (with window correction and peak-to-RMS) */
        float32_t mag = sqrtf(real * real + imag * imag);

        /**
         * Normalize magnitude:
         * 1. Window coherent gain: HANN_COHERENT_GAIN_CORRECTION / FFT_SIZE
         *    (divide out the window's energy loss)
         * 2. Peak to RMS: multiply by PEAK_TO_RMS
         * 3. Final normalization includes FFT scaling
         */
        float32_t normalization = HANN_COHERENT_GAIN_CORRECTION /
                                  (float32_t)FFT_SIZE * PEAK_TO_RMS;
        harmonics->harmonics[m].magnitude = mag * normalization;

        /* Calculate phase (degrees, relative to sine) */
        float32_t phase_rad = atan2f(imag, real);
        harmonics->harmonics[m].phase_rad = phase_rad;

        /* Store other metadata */
        harmonics->harmonics[m].order = m;
        harmonics->harmonics[m].frequency = f_harmonic;
    }
}

void goertzel_extract_harmonics_dual(
    FFTState_t *fft_state,
    const float32_t *v_signal,
    const float32_t *i_signal,
    uint16_t n_samples,
    float32_t f_measured,
    HarmonicSet_t *v_harmonics,
    HarmonicSet_t *i_harmonics
)
{
    if (!fft_state || !v_signal || !i_signal || !v_harmonics || !i_harmonics) {
        return;
    }

    /* Process voltage channel */
    goertzel_extract_harmonics(fft_state, v_signal, n_samples, f_measured, v_harmonics);

    /* Process current channel */
    goertzel_extract_harmonics(fft_state, i_signal, n_samples, f_measured, i_harmonics);
}

/* ============================================================================
 * PHASOR OPERATIONS
 * ========================================================================== */

void goertzel_phasor_multiply(
    const ComplexPhasor_t *a,
    const ComplexPhasor_t *b,
    ComplexPhasor_t *result
)
{
    if (!a || !b || !result) {
        return;
    }

    /**
     * Complex multiplication: (a + jb) * (c + jd) = (ac - bd) + j(ad + bc)
     */
    float32_t real = a->real * b->real - a->imag * b->imag;
    float32_t imag = a->real * b->imag + a->imag * b->real;

    result->real = real;
    result->imag = imag;
}

void goertzel_phasor_conjugate(
    const ComplexPhasor_t *phasor,
    ComplexPhasor_t *result
)
{
    if (!phasor || !result) {
        return;
    }

    result->real = phasor->real;
    result->imag = -phasor->imag;  /* Flip sign of imaginary part */
}

/* ============================================================================
 * DEBUG & TESTING UTILITIES
 * ========================================================================== */

#if DEBUG_FFT

/**
 * @brief Print extracted harmonics (for debugging)
 */
void goertzel_print_harmonics(const HarmonicSet_t *harmonics)
{
    if (!harmonics) {
        return;
    }

    printf("Harmonics (f_fund = %.2f Hz):\n", (double)harmonics->f_fundamental);
    printf("Order | Frequency |  Magnitude  |  Phase\n");
    printf("------|-----------|-------------|--------\n");

    for (uint16_t m = 1; m <= harmonics->n_harmonics; m++) {
        const Harmonic_t *h = &harmonics->harmonics[m];

        if (h->magnitude > 0.001f) {  /* Only print significant harmonics */
            float32_t phase_deg = h->phase_rad * 180.0f / 3.14159265f;

            printf("  %2u  | %7.1f Hz | %8.4f V | %7.1f°\n",
                   m,
                   (double)h->frequency,
                   (double)h->magnitude,
                   (double)phase_deg);
        }
    }
}

#endif /* DEBUG_FFT */
