#ifndef FENESTRA_VIDEO_QUALITY_SDK_H
#define FENESTRA_VIDEO_QUALITY_SDK_H
#include "fenestra_sdk.h"
#include "fenestra_video_quality.h"
static inline FxResult fx_sdk_video_quality_select(FxSdkClient *c,const FxServiceModule *api,
    uint64_t binding,uint32_t family,uint32_t choice) {
    FxVideoQualitySelection q={FX_VIDEO_QUALITY_ABI,sizeof(q),family,choice};
    return fx_sdk_platform(c,api,FX_BIND_CALL,binding,FX_VIDEO_QUALITY_SELECT,0u,&q,sizeof(q));
}
static inline FxResult fx_sdk_video_quality_menu(FxSdkClient *c,const FxServiceModule *api,
    uint64_t binding,uint32_t control) {
    FxVideoQualityMenu q={1u,sizeof(q),control,0u};
    return fx_sdk_platform(c,api,FX_BIND_CALL,binding,FX_VIDEO_QUALITY_MENU,0u,&q,sizeof(q));
}
#endif
