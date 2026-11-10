#ifndef FX_Z63_COLOR_JOB_H
#define FX_Z63_COLOR_JOB_H
#include "color_transplant.h"

enum {
    FX_Z63_COLOR_JOB_BYTES=0x11a20,
    FX_Z63_COLOR_CONTEXT_BYTES=0xa60,
    FX_Z63_COLOR_FRAME_BYTES=0x2cd9,
    FX_Z63_COLOR_PARAMETERS=0x1bd8,
    FX_Z63_COLOR_GENERATOR_OUTPUT=0x20e8,
    FX_Z63_COLOR_PACKED_SAMPLES=0x287c
};
typedef struct {
    void *job;
    size_t job_bytes;
    const void *context;
    size_t context_bytes;
    const void *frame;
    size_t frame_bytes;
    const void *generator_input;
    size_t generator_input_bytes;
    const void *generator_output;
    size_t generator_output_bytes;
    int32_t generator_result;
} FxZ63ColorJobView;

enum {
    FX_Z63_COLOR_JOB_STOCK=0,
    FX_Z63_COLOR_JOB_APPLIED=1,
    FX_Z63_COLOR_JOB_INVALID=-1,
    FX_Z63_COLOR_JOB_UNSUPPORTED=-2
};

/* Match the original u16 scalar interpolation, including 32-bit wrap. */
uint16_t fx_z63_color_job_interpolate(uint16_t value,uint16_t weight);

/* Return the native style index, or -1 for an invalid view. The adapter reads
 * the first pointer at A02AF8DE0 + 0x40*index to get the 25-value LUT. */
int fx_z63_color_job_style(const FxZ63ColorJobView *view);

/* Call after 4104B494 returns at the 40E72798 call site, before C+55 publication.
 * The caller must hold the recording fence and own this preparation boundary.
 * No other consumer can read or change the job during this call. C+55 is an
 * availability flag, not an ownership lock. The worker does not clear it.
 * The view must describe a fresh job whose C+55 is still zero.
 *
 * The LUT must be the current native style LUT, with 25 or more u16 values.
 * Special color paths remain unsupported. The workspace must be separate from
 * all inputs. The function retains no pointer. Stock mode makes no changes.
 * Failure leaves the native job unchanged. Success replaces its two complete
 * blocks. This binding does not establish the pixel basis or hardware order. */
int fx_z63_color_job_apply(const FxZ63ColorJobView *view,int selected,
    const uint16_t *chroma_lut,size_t chroma_values,
    const uint16_t *curve,size_t knots,FxZ63ColorCandidate *workspace);
#endif
