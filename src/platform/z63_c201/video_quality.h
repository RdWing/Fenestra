#ifndef FX_Z63_VIDEO_QUALITY_H
#define FX_Z63_VIDEO_QUALITY_H
#include "fenestra_video_quality.h"
#include "fenestra_platform.h"
#include "video_menu.h"
typedef struct {
    FxVideoQualityPolicy policy,raw;
    _Alignas(8) uint32_t mutex[4];
    _Atomic uint32_t ready,playback;
    _Atomic(FxZ63VideoMenuLease *) menu_lease;
    FxZ63VideoMenu *menu;
    FxVideoQualityPolicy h265;
    _Atomic(FxZ63VideoMenuLease *) h265_menu_lease;
    _Atomic uint32_t settings_busy,save_generation,save_sequence,save_result;

} FxZ63VideoQuality;
void fx_z63_video_init(FxZ63VideoQuality *);
FxZ63VideoQuality *fx_z63_menu_video(void);
FxZ63VideoQuality *fx_z63_menu_prepare_video(void);
FxResult fx_z63_video_resource(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,
    uint64_t *,const FxServiceRequest *,FxServiceReply *);
FxResult fx_z63_color_resource(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,uint64_t *,const FxServiceRequest *,FxServiceReply *);
FxResult fx_z63_raw_resource(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,uint64_t *,const FxServiceRequest *,FxServiceReply *);
FxResult fx_z63_h265_resource(void *,uint32_t,const FxNamedBinding *,FxPlatformOwner *,uint64_t,
    uint64_t *,const FxServiceRequest *,FxServiceReply *);
FxResult fx_z63_h265_select(FxPlatformOwner *,uint64_t,uint32_t,FxZ63VideoMenuLease *);
#endif
