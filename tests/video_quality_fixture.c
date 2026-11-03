#include "fenestra_video_quality.h"
#include <assert.h>
static void acknowledge(FxVideoQualityPolicy *s) {
    fx_video_quality_enter(s,0u,1u,1u);fx_video_quality_leave(s,0u,1u);
    fx_video_quality_enter(s,1u,1u,1u);fx_video_quality_leave(s,1u,1u);
}
int main(void) {
    FxVideoQualityPolicy s;fx_video_quality_init(&s);
    assert(atomic_load(&s.effective)==FX_VIDEO_STOCK);
    assert(fx_video_quality_select(&s,1u,FX_VIDEO_LT,1u)==FX_OK);
    assert(atomic_load(&s.effective)==FX_VIDEO_STOCK); /* unobserved native owners */
    acknowledge(&s);assert(atomic_load(&s.effective)==FX_VIDEO_LT);
    assert(fx_video_quality_select(&s,2u,FX_VIDEO_PROXY,1u)==FX_BUSY);
    assert(s.requested==FX_VIDEO_LT && s.owner==1u);
    fx_video_quality_enter(&s,0u,1u,1u);
    assert(fx_video_quality_select(&s,1u,FX_VIDEO_STANDARD,1u)==FX_OK);
    assert(atomic_load(&s.effective)==FX_VIDEO_LT);
    fx_video_quality_leave(&s,0u,0u);assert(atomic_load(&s.effective)==FX_VIDEO_LT);
    fx_video_quality_commit(&s,0u);assert(atomic_load(&s.effective)==FX_VIDEO_LT);
    fx_video_quality_commit(&s,1u);assert(atomic_load(&s.effective)==FX_VIDEO_STANDARD);
    fx_video_quality_enter(&s,1u,1u,1u);fx_video_quality_enter(&s,1u,0u,0u);
    assert(fx_video_quality_release(&s,1u,1u)==FX_BUSY);
    assert(s.owner==1u && atomic_load(&s.effective)==FX_VIDEO_STANDARD);
    assert(fx_video_quality_select(&s,1u,FX_VIDEO_HQ,1u)==FX_STATE);
    fx_video_quality_leave(&s,1u,1u);assert(s.owner==1u);
    fx_video_quality_leave(&s,1u,1u);assert(!s.owner && atomic_load(&s.effective)==FX_VIDEO_STOCK);
    assert(fx_video_quality_select(&s,2u,FX_VIDEO_PROXY,1u)==FX_OK);
    assert(fx_video_quality_select(&s,2u,5u,1u)==FX_ARGUMENT);
    assert(s.requested==FX_VIDEO_PROXY);
    assert(fx_video_quality_release(&s,1u,1u)==FX_OK && s.owner==2u);
    fx_video_quality_leave(&s,0u,1u);assert(s.fault);
    assert(fx_video_quality_select(&s,2u,FX_VIDEO_STOCK,1u)==FX_STATE);
    assert(atomic_load(&s.effective)==FX_VIDEO_PROXY); /* uncertain work: retain coherent choice */
    fx_video_quality_init(&s);s.registered=3u;s.active[0]=UINT32_MAX;
    fx_video_quality_enter(&s,0u,1u,1u);assert(s.fault && s.active[0]==UINT32_MAX);
    return 0;
}
