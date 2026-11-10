#include <assert.h>
#include <string.h>
#include "../src/platform/z63_c201/video_quality.h"
#include "fenestra_video_color.h"
int main(void) {
    FxPlatformOwner owner={0};
    FxServiceRequest q={0};FxServiceReply a={0};uint64_t cookie=0;
    for(uint32_t family=2;family<=2;++family) {
        FxResult (*call)(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,uint64_t *,const FxServiceRequest *,FxServiceReply *)=
            fx_z63_color_resource;
        assert(call(0,FX_RESOURCE_ATTACH,0,&owner,7,&cookie,0,0)==FX_OK);
        q.arg[2]=FX_VIDEO_QUALITY_QUERY;q.bytes=0;
        assert(call(0,FX_RESOURCE_CALL,0,&owner,7,&cookie,&q,&a)==FX_OK);
        FxVideoQualityInfo info;memcpy(&info,a.data,sizeof(info));
        assert(info.family==family && info.choices==1 && (info.flags&FX_VIDEO_QUALITY_UNAVAILABLE));
        q.arg[2]=FX_VIDEO_QUALITY_SELECT;
        assert(call(0,FX_RESOURCE_CALL,0,&owner,7,&cookie,&q,&a)==FX_CAPABILITY);
        q.arg[2]=FX_VIDEO_QUERY_PATH;q.bytes=4;
        for(uint32_t path=0;path<=FX_VIDEO_PATH_COUNT;++path) {
            memcpy(q.data,&path,4);
            FxResult result=call(0,FX_RESOURCE_CALL,0,&owner,7,&cookie,&q,&a);
            if(path==FX_VIDEO_PATH_COUNT){assert(result==FX_ARGUMENT);continue;}
            assert(result==FX_OK);FxVideoPathInfo pi;memcpy(&pi,a.data,sizeof(pi));
            assert(pi.path==path && !pi.supported && !pi.ei_available && pi.reason);
        }
        assert(call(0,FX_RESOURCE_CALL,0,&owner,8,&cookie,&q,&a)==FX_STALE);
        assert(call(0,FX_RESOURCE_DETACH,0,&owner,7,&cookie,0,0)==FX_OK && !cookie);
    }
    return 0;
}
