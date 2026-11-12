#include "fenestra_video_recording.h"
#include "fenestra_memory.h"
_Static_assert(ATOMIC_LLONG_LOCK_FREE==2,"recording configuration must be lock free");
void fx_video_recording_init(FxVideoRecording *r) {
    memset(r,0,sizeof(*r));atomic_init(&r->configuration,0);atomic_init(&r->fault,0);
}
uint64_t fx_video_recording_read(const FxVideoRecording *r) {
    return r?atomic_load_explicit(&r->configuration,memory_order_acquire):0;
}
FxResult fx_video_recording_begin(FxVideoRecording *r,uint32_t type,uint32_t tier) {
    if(!r || type<1u || type>6u || tier>4u)return FX_ARGUMENT;
    uint64_t previous=fx_video_recording_read(r);
    if(previous) {
        if(r->duplicates!=UINT32_MAX)++r->duplicates;
        /* Coalesced/repeated preparation keeps the first immutable choice.
         * A conflicting format is uncertain ownership, never a new epoch. */
        if((uint32_t)((previous>>8)&255u)!=type || r->cleared_generation==(uint32_t)(previous>>32)) {
            atomic_store(&r->fault,1u);return FX_INTEGRITY;
        }
        return FX_OK;
    }
    if(atomic_load(&r->fault))return FX_STATE;
    if(r->generation!=UINT32_MAX)++r->generation;
    else atomic_store(&r->fault,1u); /* Retain this final lease; never wrap/reuse. */
    r->cleared_generation=0;
    if(r->copies!=UINT32_MAX)++r->copies;
    uint32_t h265=type==2u || type==3u;
    uint64_t config=(uint64_t)r->generation<<32|(uint64_t)type<<8|(uint64_t)(h265?tier:0u)<<1|1u;
    atomic_store_explicit(&r->configuration,config,memory_order_release);
    return atomic_load(&r->fault)?FX_BOUNDS:FX_OK;
}
void fx_video_recording_clear(FxVideoRecording *r,uint64_t configuration,int verified) {
    if(!r || !configuration)return;
    if(!verified || fx_video_recording_read(r)!=configuration) {
        atomic_store(&r->fault,1u);return;
    }
    r->cleared_generation=(uint32_t)(configuration>>32);
}
int fx_video_recording_retire(FxVideoRecording *r,int native_idle,uint32_t movie_calls,uint32_t capture_calls) {
    if(!r)return 0;
    uint64_t config=fx_video_recording_read(r);
    if(!config)return !atomic_load(&r->fault);
    if(atomic_load(&r->fault) || !native_idle || movie_calls || capture_calls ||
       r->cleared_generation!=(uint32_t)(config>>32))return 0;
    atomic_store_explicit(&r->configuration,0,memory_order_release);
    if(r->retired!=UINT32_MAX)++r->retired;
    return 1;
}
uint32_t fx_video_recording_tier(uint64_t config,uint32_t type) {
    if(!(config&1u) || !(config>>32) || (type!=2u && type!=3u) || ((config>>8)&255u)!=type)return 0;
    uint32_t tier=(uint32_t)((config>>1)&7u);return tier<=4u?tier:0u;
}
