/**
 * @file mock_arm_math.h
 * @brief Mock CMSIS-DSP functions for host testing
 *
 * Implements essential DSP functions using standard C math
 * for testing without ARM hardware
 */

#ifndef MOCK_ARM_MATH_H
#define MOCK_ARM_MATH_H

#include <math.h>
#include <stdint.h>
#include <string.h>

typedef float float32_t;
typedef int32_t q31_t;
typedef int arm_status;

#define ARM_MATH_SUCCESS 0

/* ============================================================================
 * RMS CALCULATION - arm_rms_f32
 * ========================================================================== */

static inline void arm_rms_f32(
    const float32_t *pSrc,
    uint32_t blockSize,
    float32_t *pResult)
{
    float32_t sum = 0.0f;

    for (uint32_t i = 0; i < blockSize; i++) {
        sum += pSrc[i] * pSrc[i];
    }

    *pResult = sqrtf(sum / (float32_t)blockSize);
}

/* ============================================================================
 * BIQUAD IIR FILTER - arm_biquad_cascade_df1_f32
 * ========================================================================== */

typedef struct {
    uint8_t numStages;
    float32_t *pState;
    float32_t *pCoeffs;
} arm_biquad_cascade_df1_instance_f32;

static inline void arm_biquad_cascade_df1_f32(
    const arm_biquad_cascade_df1_instance_f32 *S,
    const float32_t *pSrc,
    float32_t *pDst,
    uint32_t blockSize)
{
    if (!S || !pSrc || !pDst) return;

    const float32_t *pCoeffs = S->pCoeffs;
    float32_t *pState = S->pState;
    uint32_t numStages = S->numStages;
    float32_t *pStateCurnt;
    float32_t input;
    float32_t output;
    float32_t b0, b1, b2, a1, a2;
    float32_t xn1, xn2, yn1, yn2;
    uint32_t sample, stage;

    for (stage = 0; stage < numStages; stage++) {
        pStateCurnt = pState + (stage * 4U);
        b0 = *pCoeffs++;
        b1 = *pCoeffs++;
        b2 = *pCoeffs++;
        a1 = *pCoeffs++;
        a2 = *pCoeffs++;

        xn1 = pStateCurnt[0];
        xn2 = pStateCurnt[1];
        yn1 = pStateCurnt[2];
        yn2 = pStateCurnt[3];

        for (sample = 0; sample < blockSize; sample++) {
            input = (stage == 0) ? pSrc[sample] : pDst[sample];

            output = b0 * input + b1 * xn1 + b2 * xn2 - a1 * yn1 - a2 * yn2;

            xn2 = xn1;
            xn1 = input;
            yn2 = yn1;
            yn1 = output;

            pDst[sample] = output;
        }

        pStateCurnt[0] = xn1;
        pStateCurnt[1] = xn2;
        pStateCurnt[2] = yn1;
        pStateCurnt[3] = yn2;
    }
}

/* ============================================================================
 * COMPLEX MULTIPLICATION - arm_cmplx_mult_f32
 * ========================================================================== */

static inline void arm_cmplx_mult_f32(
    const float32_t *pSrcA,
    const float32_t *pSrcB,
    float32_t *pDst,
    uint32_t numSamples)
{
    for (uint32_t i = 0; i < numSamples; i++) {
        float32_t a_real = pSrcA[2*i];
        float32_t a_imag = pSrcA[2*i + 1];
        float32_t b_real = pSrcB[2*i];
        float32_t b_imag = pSrcB[2*i + 1];

        /* (a + bi) * (c + di) = (ac - bd) + (ad + bc)i */
        pDst[2*i]     = a_real * b_real - a_imag * b_imag;
        pDst[2*i + 1] = a_real * b_imag + a_imag * b_real;
    }
}

/* ============================================================================
 * REAL FFT - Simplified Mock
 * ========================================================================== */

typedef struct {
    uint16_t fftLen;
    float32_t *pTwiddle;
    uint8_t *pBitRevTable;
} arm_rfft_fast_instance_f32;

/* Simple DFT implementation for testing (not optimized like FFT) */
static inline void arm_rfft_fast_f32(
    const arm_rfft_fast_instance_f32 *S,
    float32_t *pSrc,
    float32_t *pDst,
    uint8_t ifftFlag)
{
    if (!S || !pSrc || !pDst) return;

    uint32_t N = S->fftLen;
    float32_t pi = 3.14159265358979f;

    for (uint32_t k = 0; k < N; k++) {
        float32_t real = 0.0f, imag = 0.0f;

        for (uint32_t n = 0; n < N; n++) {
            float32_t angle = -2.0f * pi * k * n / N;
            if (ifftFlag) angle = -angle;

            float32_t cosv = cosf(angle);
            float32_t sinv = sinf(angle);

            real += pSrc[n] * cosv;
            imag += pSrc[n] * sinv;
        }

        if (ifftFlag) {
            real /= N;
            imag /= N;
        }

        pDst[2*k]     = real;
        pDst[2*k + 1] = imag;
    }
}

static inline arm_status arm_rfft_fast_init_f32(
    arm_rfft_fast_instance_f32 *S,
    uint16_t fftLen)
{
    S->fftLen = fftLen;
    return 0;  /* ARM_MATH_SUCCESS */
}

#endif /* MOCK_ARM_MATH_H */
