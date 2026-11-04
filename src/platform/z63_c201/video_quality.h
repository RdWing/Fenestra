#ifndef FX_Z63_VIDEO_QUALITY_H
#define FX_Z63_VIDEO_QUALITY_H
#include "fenestra_video_quality.h"
#include "fenestra_platform.h"
#include "video_menu.h"
typedef struct {
    FxVideoQualityPolicy policy;
    _Alignas(8) uint32_t mutex[4];
    _Atomic uint32_t ready,playback;
    _Atomic(FxZ63VideoMenuLease *) menu_lease;
    FxZ63VideoMenu *menu;
} FxZ63VideoQuality;
void fx_z63_video_init(FxZ63VideoQuality *);
FxZ63VideoQuality *fx_z63_menu_video(void);
FxZ63VideoQuality *fx_z63_menu_prepare_video(void);
FxResult fx_z63_video_resource(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,
    uint64_t *,const FxServiceRequest *,FxServiceReply *);
#endif
