#include "video_quality.h"
#include "fenestra_memory.h"

/* These providers expose the missing joins without publishing a false active
 * state. They cannot modify tables, gain, metadata, or the ProRes lease. */
#include "fenestra_video_color.h"
static FxResult color_raw_resource(uint32_t family,uint32_t op,FxPlatformOwner *owner,
    uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    if(!owner || !token || !cookie)return FX_ARGUMENT;
    if(op==FX_RESOURCE_ATTACH){*cookie=token;return FX_OK;}
    if(*cookie!=token)return FX_STALE;
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC){*cookie=0u;return FX_OK;}
    if(op!=FX_RESOURCE_CALL || !q || !a || q->arg[3])return FX_ARGUMENT;
    if(!q->bytes && q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
        FxVideoQualityInfo info={1u,sizeof(info),family,1u,
            FX_VIDEO_QUALITY_SESSION_ONLY|FX_VIDEO_QUALITY_EXPERIMENTAL|FX_VIDEO_QUALITY_UNAVAILABLE,0u};
        memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);return FX_OK;
    }
    if(!q->bytes && q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
        FxVideoQualityStatus status={0};status.abi=1u;status.bytes=sizeof(status);status.family=family;
        memcpy(a->data,&status,sizeof(status));a->bytes=sizeof(status);return FX_OK;
    }
    if(q->arg[2]==FX_VIDEO_QUERY_PATH && q->bytes==sizeof(uint32_t)) {
        uint32_t path;memcpy(&path,q->data,sizeof(path));
        if(path>=FX_VIDEO_PATH_COUNT)return FX_ARGUMENT;
        FxVideoPathInfo info={1u,sizeof(info),path,0u,
            family==FX_VIDEO_FAMILY_COLOR?FX_VIDEO_REASON_COLOR_JOIN:FX_VIDEO_REASON_WRITER_JOIN,0u,0u,0u};
        memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);return FX_OK;
    }
    return FX_CAPABILITY;
}
FxResult fx_z63_color_resource(void *context,uint32_t op,const FxNamedBinding *binding,
    FxPlatformOwner *owner,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)binding;
    return color_raw_resource(FX_VIDEO_FAMILY_COLOR,op,owner,token,cookie,q,a);
}
