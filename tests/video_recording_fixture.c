#include "fenestra_video_recording.h"
#include <assert.h>
int main(void) {
    for(uint32_t type=1;type<=6;++type)for(uint32_t tier=0;tier<5;++tier) {
        FxVideoRecording r;fx_video_recording_init(&r);
        assert(fx_video_recording_begin(&r,type,tier)==FX_OK);
        uint64_t snapshot=fx_video_recording_read(&r);
        uint32_t expected=type==2 || type==3?tier:0;
        assert(fx_video_recording_tier(snapshot,type)==expected);
        for(uint32_t next=0;next<5;++next) {
            assert(fx_video_recording_begin(&r,type,next)==FX_OK);
            assert(fx_video_recording_read(&r)==snapshot);
        }
        assert(!fx_video_recording_retire(&r,1,0,0)); /* Idle alone is insufficient. */
        fx_video_recording_clear(&r,snapshot,1);
        assert(!fx_video_recording_retire(&r,0,0,0));
        assert(!fx_video_recording_retire(&r,1,1,0));
        assert(!fx_video_recording_retire(&r,1,0,1));
        assert(fx_video_recording_retire(&r,1,0,0));
        assert(!fx_video_recording_read(&r) && r.retired==1);
        assert(fx_video_recording_begin(&r,type,(tier+1)%5)==FX_OK);
        assert(fx_video_recording_read(&r)!=snapshot);
        fx_video_recording_clear(&r,snapshot,1); /* A late clear cannot release a new recording. */
        assert(r.fault && !fx_video_recording_retire(&r,1,0,0));
    }
    FxVideoRecording r;fx_video_recording_init(&r);
    assert(fx_video_recording_begin(&r,0,0)==FX_ARGUMENT && !fx_video_recording_read(&r));
    assert(fx_video_recording_begin(&r,3,5)==FX_ARGUMENT);
    assert(fx_video_recording_begin(&r,3,1)==FX_OK);
    uint64_t old=fx_video_recording_read(&r);
    assert(fx_video_recording_begin(&r,2,4)==FX_INTEGRITY && fx_video_recording_read(&r)==old);
    fx_video_recording_clear(&r,old,1);assert(!fx_video_recording_retire(&r,1,0,0));
    fx_video_recording_init(&r);r.generation=UINT32_MAX;
    assert(fx_video_recording_begin(&r,3,4)==FX_BOUNDS);
    old=fx_video_recording_read(&r);assert(old>>32==UINT32_MAX && fx_video_recording_tier(old,3)==4);
    fx_video_recording_clear(&r,old,1);assert(!fx_video_recording_retire(&r,1,0,0));
    return 0;
}
