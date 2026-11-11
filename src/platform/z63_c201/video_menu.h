#ifndef FX_Z63_VIDEO_MENU_H
#define FX_Z63_VIDEO_MENU_H
#include "fenestra_native_menu.h"
#include "fenestra_video_quality.h"
#define FX_Z63_VIDEO_MENU_PAGE 0x7060u
#define FX_Z63_VIDEO_MENU_TEXTS 32u
typedef struct FxZ63VideoMenu FxZ63VideoMenu;
typedef struct {
    FxPlatformOwner *owner;uint64_t token;uint32_t control;_Atomic uint32_t active;uint32_t family;
} FxZ63VideoMenuLease;
FxResult fx_z63_video_menu_bind(FxPlatformOwner *,uint64_t,uint32_t,uint32_t);
void fx_z63_video_menu_unbind(FxPlatformOwner *,uint64_t);
FxResult fx_z63_video_menu_select(FxZ63VideoMenuLease *,uint32_t);
FxResult fx_z63_video_menu_status(FxZ63VideoMenuLease *,FxVideoQualityStatus *);
FxNativePage *fx_z63_video_menu_parent(FxNativePage *,const FxNativeEvent *,const FxNativeRow *);
FxNativePage *fx_z63_video_menu_page(uint32_t);
int fx_z63_video_menu_visible(const FxNativePage *);
int fx_z63_video_menu_text(uint32_t,const uint16_t **,uint32_t *);
FxResult fx_z63_video_menu_flush(FxPlatformOwner *,FxNativePage *,uint32_t *);
uint32_t fx_z63_ui_video_text_base(void);
#endif
