#include "fenestra_video_quality.h"
#include "fenestra_memory.h"
void fx_video_quality_init(FxVideoQualityPolicy *s) {
    memset(s,0,sizeof(*s));atomic_init(&s->effective,FX_VIDEO_STOCK);atomic_init(&s->fault,0u);
}
void fx_video_quality_commit(FxVideoQualityPolicy *s,uint32_t idle) {
    if(!idle || s->fault || s->registered!=3u || s->active[0] || s->active[1])return;
    uint32_t next=s->retiring?FX_VIDEO_STOCK:s->requested;
    if(atomic_load_explicit(&s->effective,memory_order_relaxed)!=next) {
        atomic_store_explicit(&s->effective,next,memory_order_release);++s->transitions;
    }
    if(s->retiring){s->owner=0u;s->requested=FX_VIDEO_STOCK;s->retiring=0u;}
}
FxResult fx_video_quality_select(FxVideoQualityPolicy *s,uint64_t owner,uint32_t choice,uint32_t idle) {
    if(!s || !owner || choice>FX_VIDEO_PROXY)return FX_ARGUMENT;
    if(s->fault || s->retiring)return FX_STATE;
    if(s->owner && s->owner!=owner)return FX_BUSY;
    s->owner=owner;s->requested=choice;fx_video_quality_commit(s,idle);return FX_OK;
}
FxResult fx_video_quality_release(FxVideoQualityPolicy *s,uint64_t owner,uint32_t idle) {
    if(!s || !owner)return FX_ARGUMENT;
    if(s->owner!=owner)return FX_OK;
    s->retiring=1u;s->requested=FX_VIDEO_STOCK;fx_video_quality_commit(s,idle);
    return s->owner?FX_BUSY:FX_OK;
}
void fx_video_quality_enter(FxVideoQualityPolicy *s,uint32_t domain,uint32_t acknowledge,uint32_t idle) {
    if(!s || domain>1u)return;
    if(acknowledge)s->registered|=1u<<domain;
    fx_video_quality_commit(s,idle);
    if(s->active[domain]==UINT32_MAX){s->fault=1u;return;}
    ++s->active[domain];
}
void fx_video_quality_leave(FxVideoQualityPolicy *s,uint32_t domain,uint32_t idle) {
    if(!s || domain>1u)return;
    if(!s->active[domain]){s->fault=1u;return;}
    --s->active[domain];fx_video_quality_commit(s,idle);
}
