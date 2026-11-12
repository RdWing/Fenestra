#ifndef FENESTRA_VIDEO_RECORDING_H
#define FENESTRA_VIDEO_RECORDING_H
#include "fenestra.h"
#include <stdatomic.h>
/* One native capture-buffer lifetime, not one count per posted event bit.
 * Mutators share the video's admission mutex; readers copy one atomic value.
 * No pointer to mutable settings is retained in a recording configuration. */
typedef struct {
    _Atomic uint64_t configuration;
    uint32_t generation,cleared_generation;
    _Atomic uint32_t fault;
    uint32_t copies,duplicates,retired;
} FxVideoRecording;
void fx_video_recording_init(FxVideoRecording *);
FxResult fx_video_recording_begin(FxVideoRecording *,uint32_t type,uint32_t tier);
void fx_video_recording_clear(FxVideoRecording *,uint64_t configuration,int verified);
int fx_video_recording_retire(FxVideoRecording *,int native_idle,uint32_t movie_calls,uint32_t capture_calls);
uint64_t fx_video_recording_read(const FxVideoRecording *);
uint32_t fx_video_recording_tier(uint64_t configuration,uint32_t type);
#endif
