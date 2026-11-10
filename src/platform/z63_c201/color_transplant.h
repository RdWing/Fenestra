#ifndef FX_Z63_COLOR_TRANSPLANT_H
#define FX_Z63_COLOR_TRANSPLANT_H
#include <stddef.h>
#include <stdint.h>

/* Private output for offline comparison with the ZR tone-3 producers.
 * It has no native consumer or recording lease. The caller owns its lifetime. */
typedef struct {
    uint8_t parameters[0x408];
    uint8_t samples[0x2a8e];
} FxZ63ColorCandidate;

/* Supply a complete stock N-Log job and the recovered ZR curve. chroma_q10
 * is the native M2 producer's interpolated scalar, before coefficient rounding.
 * Failure leaves output unchanged. Input and output storage must not overlap.
 * This prepares a test candidate; it does not admit or publish a camera job. */
int fx_z63_color_transplant(FxZ63ColorCandidate *output,
    const void *parameters,size_t parameter_bytes,const void *samples,size_t sample_bytes,
    const uint16_t *curve,size_t knots,uint16_t chroma_q10);

/* Complete Z8-method configuration for offline C2.01 writer tests. m1_q10
 * contains effective coefficients, after body composition. The caller must
 * establish the basis and scale; this API does not qualify a fitted matrix.
 * All six curves, NLG, M1, M2 and both CPXS sets change together in private
 * storage. Preserve the stock N-Log routing controls. No publication occurs. */
int fx_z63_color_rwg_candidate(FxZ63ColorCandidate *output,
    const void *parameters,size_t parameter_bytes,const void *samples,size_t sample_bytes,
    const int16_t *m1_q10,size_t coefficients,const uint16_t *curve,size_t knots);
#endif
