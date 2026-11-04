#include "video_quality.h"
#include "ui.h"
#include "fenestra_memory.h"
#include "fenestra_native_text.h"
#include "fenestra_native_ui_callbacks.h"
#include "fenestra_native_ui_dispatch.h"
#include "fenestra_native_visibility.h"
#include "fenestra_native_display.h"
#define ROOT_PAGE 266u
#define ROOT_ROW 0x7f50u
#define CHOICE_ROW 0x7f60u
struct FxZ63VideoMenu {
    FxNativeDescriptor descriptor;
    FxNativeRow rows[46];uintptr_t events[46];
    uintptr_t callbacks[5],original_callbacks[5];
    const FxNativeDescriptor *original;
    FxNativeEvent link[FX_NATIVE_EVENTS];
    FxNativeMenu choices;
    FxNativePage *parent;
    uint32_t refresh_calls,refresh_result;uintptr_t observed_page;
};
__attribute__((used,retain)) const uint32_t fx_z63_video_menu_layout[]={0x4658564du,1u,offsetof(FxZ63VideoQuality,menu),
    offsetof(FxZ63VideoMenu,refresh_calls),offsetof(FxZ63VideoMenu,refresh_result),offsetof(FxZ63VideoMenu,observed_page)};
extern void *fx_z63_current_page(void);
static void *allocate(uint32_t bytes){return ((void *(*)(uint32_t,uint32_t))(uintptr_t)0x40d32d00u)(bytes,0u);}
static FxZ63VideoMenuLease *lease(void) {
    FxZ63VideoQuality *s=fx_z63_menu_video();return s?atomic_load_explicit(&s->menu_lease,memory_order_acquire):0;
}
static int live(FxZ63VideoMenuLease *l){return l && atomic_load_explicit(&l->active,memory_order_acquire) && l->owner->phase==FX_OWNER_RUNNING;}
static uint32_t format(void){return ((uint32_t (*)(uint32_t))(uintptr_t)0x403ffcd0u)(0x06000f06u);}
static uint32_t allowed(void *context){(void)context;return live(lease()) && format()==4u;}
static uint32_t noop(void *context){(void)context;return 1u;}
FxResult fx_z63_video_menu_bind(FxPlatformOwner *owner,uint64_t token,uint32_t control) {
    if(!owner || !token || !control)return FX_ARGUMENT;
    FxUiControl controls[FX_UI_CONTROLS];uint32_t count=0u,revision=0u;
    FxResult result=fx_ui_snapshot(owner,controls,FX_UI_CONTROLS,&count,&revision);if(result!=FX_OK)return result;
    uint32_t found=0u;
    for(uint32_t i=0u;i<count;++i)if(controls[i].id==control && controls[i].kind==FX_UI_CHOICE && controls[i].option_count==5u)found=1u;
    if(!found)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s)return FX_STATE;
    FxZ63VideoMenuLease *old=lease();
    if(old && atomic_load(&old->active))return old->owner==owner && old->token==token && old->control==control?FX_OK:FX_BUSY;
    FxZ63VideoMenuLease *l=allocate(sizeof(*l));if(!l)return FX_BUDGET;
    *l=(FxZ63VideoMenuLease){.owner=owner,.token=token,.control=control};atomic_init(&l->active,1u);
    atomic_store_explicit(&s->menu_lease,l,memory_order_release);return FX_OK;
}
void fx_z63_video_menu_unbind(FxPlatformOwner *owner,uint64_t token) {
    FxZ63VideoMenuLease *l=lease();if(l && l->owner==owner && l->token==token)atomic_store_explicit(&l->active,0u,memory_order_release);
}
static uint32_t choose(uint32_t value) {
    FxZ63VideoMenuLease *l=lease();if(!allowed(0))return 0u;
    FxResult result=fx_z63_video_menu_select(l,value);
    if(result==FX_OK)fx_native_ui_refresh_owner(l->owner);
    return result==FX_OK;
}
static uint32_t stock(void *p){(void)p;return choose(0u);}
static uint32_t hq(void *p){(void)p;return choose(1u);}
static uint32_t standard(void *p){(void)p;return choose(2u);}
static uint32_t lt(void *p){(void)p;return choose(3u);}
static uint32_t proxy(void *p){(void)p;return choose(4u);}
static const FxNativeTextProfile text_profile={(uintptr_t)fx_z63_current_page,0x40331b28u,0x4032b8bcu,
    0x404054a8u,0x404054e8u,0x40337910u,0x4032b3dcu,0x4dc0u,0x1c0u,0x118u,0x404056b0u,0u,0u};
static FxResult refresh(FxZ63VideoMenu *m) {
    if(!m)return FX_EMPTY;
    ++m->refresh_calls;m->observed_page=(uintptr_t)fx_z63_current_page();
    if(m->observed_page!=(uintptr_t)m->parent){m->refresh_result=FX_EMPTY;return FX_EMPTY;}
    FxVideoQualityStatus status={0};FxResult result=fx_z63_video_menu_status(lease(),&status);
    uint32_t enabled=allowed(0) && result==FX_OK && !status.fault;
    uint32_t base=fx_z63_ui_video_text_base(),value=enabled?(status.pending?base+6u:base+1u+status.requested):base+7u;
    result=fx_native_text_prepare(&text_profile,m->parent,ROOT_ROW,base,value,enabled,0);
    m->refresh_result=(uint32_t)result;return result;
}
static uint64_t root_open(void *window) {
    FxZ63VideoQuality *s=fx_z63_menu_video();FxZ63VideoMenu *m=s?s->menu:0;if(!m)return 1u;
    uint64_t result=((uint64_t (*)(void *))m->original_callbacks[0])(window);FxResult prepared=refresh(m);FxZ63VideoMenuLease *l=lease();
    if(prepared!=FX_OK && live(l))fx_native_ui_refresh_owner(l->owner);return result;
}
static uint64_t root_refresh(void *window) {
    FxZ63VideoQuality *s=fx_z63_menu_video();FxZ63VideoMenu *m=s?s->menu:0;if(!m)return 1u;
    uint64_t result=((uint64_t (*)(void *))m->original_callbacks[4])(window);FxResult prepared=refresh(m);FxZ63VideoMenuLease *l=lease();
    if(prepared!=FX_OK && live(l))fx_native_ui_refresh_owner(l->owner);return result;
}
static uint32_t choice_open(void *page){(void)page;fx_native_ui_capture_task();return 1u;}
FxNativePage *fx_z63_video_menu_parent(FxNativePage *page,const FxNativeEvent *navigation,const FxNativeRow *choice_row) {
    if(!choice_row || !page || page->identity!=((ROOT_PAGE<<16)|2u))return page;
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s)return page;
    FxZ63VideoMenu *m=s->menu;
    if(!live(lease())) {
        if(m && page->descriptor==(uintptr_t)&m->descriptor && fx_z63_current_page()!=page) {
            page->descriptor=(uintptr_t)m->original;page->callbacks=(uintptr_t)UINT64_C(0xa028f55e0);
        }
        return page;
    }
    if(m) {
        if(page->descriptor==(uintptr_t)m->original){page->callbacks=(uintptr_t)m->callbacks;page->descriptor=(uintptr_t)&m->descriptor;}
        return page;
    }
    const FxNativeDescriptor *source=(const void *)page->descriptor;
    if(page->descriptor!=UINT64_C(0xa028cae10) || source->count!=45u ||
       source->header!=UINT64_C(0x43cb3758) || source->rows!=UINT64_C(0x43cb3868) || source->events!=UINT64_C(0x43cb4028) ||
       page->callbacks!=UINT64_C(0xa028f55e0))return page;
    const FxNativeRow *rows=(const void *)source->rows;if(rows[9].word[0]!=2185u)return page;
    uint32_t base=fx_z63_ui_video_text_base();if(fx_z63_menu_text_ensure(base+FX_Z63_VIDEO_MENU_TEXTS)!=FX_OK)return page;
    if(fx_z63_menu_text_style(base,FX_Z63_VIDEO_MENU_TEXTS,2185u)!=FX_OK)return page;
    m=allocate(sizeof(*m));if(!m)return page;memset(m,0,sizeof(*m));m->parent=page;m->original=source;m->descriptor=*source;
    memcpy(m->original_callbacks,(const void *)page->callbacks,sizeof(m->callbacks));memcpy(m->callbacks,m->original_callbacks,sizeof(m->callbacks));
    m->callbacks[0]=(uintptr_t)root_open;m->callbacks[4]=(uintptr_t)root_refresh;
    memcpy(m->rows,rows,10u*sizeof(*rows));memcpy(m->rows+11u,rows+10u,35u*sizeof(*rows));
    const uintptr_t *events=(const void *)source->events;
    memcpy(m->events,events,10u*sizeof(*events));memcpy(m->events+11u,events+10u,35u*sizeof(*events));
    m->rows[10]=*choice_row;m->rows[10].word[4]|=0x41u;m->rows[10].word[0]=base;m->rows[10].word[2]=65535u;m->rows[10].word[6]=ROOT_ROW;
    uint32_t selects[4]={0x2b3u,0x2b8u,0x2ccu,0x2dbu};
    if(fx_native_menu_link(m->link,navigation,0x3f2u,selects,(uintptr_t)noop,FX_Z63_VIDEO_MENU_PAGE)!=FX_OK)return page;
    for(uint32_t i=0u;i<FX_NATIVE_EVENTS && m->link[i].event!=0x3f2u;++i)
        for(uint32_t k=0u;k<4u;++k)if(m->link[i].event==selects[k])m->link[i].condition=(uintptr_t)allowed;
    m->events[10]=(uintptr_t)m->link;m->descriptor.rows=(uintptr_t)m->rows;m->descriptor.events=(uintptr_t)m->events;m->descriptor.count=46u;
    FxNativeMenuProfile profile={page,choice_row,navigation,0x3f2u,0x2abu,{0x2b3u,0x2b8u,0x2ccu,0x2dbu},0x712u,ROOT_PAGE};
    uintptr_t callbacks[5]={(uintptr_t)choice_open,(uintptr_t)noop,m->original_callbacks[2],(uintptr_t)noop,(uintptr_t)noop};
    uintptr_t actions[5]={(uintptr_t)stock,(uintptr_t)hq,(uintptr_t)standard,(uintptr_t)lt,(uintptr_t)proxy};FxNativeEntry entries[6];
    for(uint32_t i=0u;i<5u;++i)entries[i]=(FxNativeEntry){base+1u+i,CHOICE_ROW+i,0u,0u,actions[i],ROOT_PAGE};
    entries[5]=(FxNativeEntry){base+8u,CHOICE_ROW+5u,0u,0u,(uintptr_t)noop,ROOT_PAGE};
    if(fx_native_menu_build(&m->choices,&profile,FX_Z63_VIDEO_MENU_PAGE,base,entries,6u,callbacks)!=FX_OK)return page;
    for(uint32_t row=0u;row<5u;++row)for(uint32_t event=0u;event<FX_NATIVE_EVENTS;++event) {
        if(m->choices.handlers[row][event].event==profile.terminal)break;
        for(uint32_t k=0u;k<4u;++k)if(m->choices.handlers[row][event].event==selects[k]) {
            m->choices.handlers[row][event].condition=actions[row];m->choices.handlers[row][event].callback=(uintptr_t)noop;
        }
    }
    s->menu=m;page->callbacks=(uintptr_t)m->callbacks;atomic_store_explicit((_Atomic uintptr_t *)&page->descriptor,(uintptr_t)&m->descriptor,memory_order_release);
    return page;
}
int fx_z63_video_menu_visible(const FxNativePage *page) {
    FxZ63VideoQuality *s=fx_z63_menu_video();FxZ63VideoMenu *m=s?s->menu:0;
    return m && (page==m->parent || page==&m->choices.page);
}
FxNativePage *fx_z63_video_menu_page(void) {
    FxZ63VideoQuality *s=fx_z63_menu_video();FxZ63VideoMenu *m=s?s->menu:0;
    if(!m || !allowed(0))return 0;
    FxVideoQualityStatus status={0};if(fx_z63_video_menu_status(lease(),&status)!=FX_OK)return 0;
    m->choices.page.selected=(uint16_t)(status.requested<=4u?status.requested:0u);return &m->choices.page;
}
int fx_z63_video_menu_text(uint32_t id,const uint16_t **out,uint32_t *bytes) {
    uint32_t base=fx_z63_ui_video_text_base();if(id<base || id>base+8u)return 0;
    static const uint16_t label[]={'V','i','d','e','o',' ','q','u','a','l','i','t','y',' ','(','P','r','o','R','e','s',')',0};
    static const uint16_t stock_text[]={'S','t','o','c','k',0},hq_text[]={'H','Q',0},standard_text[]={'S','t','a','n','d','a','r','d',0};
    static const uint16_t lt_text[]={'L','T',0},proxy_text[]={'P','r','o','x','y',0},pending[]={'W','a','i','t','i','n','g',0},empty[]={0},back[]={'B','a','c','k',0};
    const uint16_t *labels[]={label,stock_text,hq_text,standard_text,lt_text,proxy_text,pending,empty,back};
    *out=labels[id-base];uint32_t n=0u;while((*out)[n])++n;*bytes=n*2u;return 1;
}
FxResult fx_z63_video_menu_flush(FxPlatformOwner *owner,FxNativePage *page,uint32_t *destination) {
    FxZ63VideoQuality *s=fx_z63_menu_video();FxZ63VideoMenu *m=s?s->menu:0;FxZ63VideoMenuLease *l=lease();
    if(!m || !l || l->owner!=owner || !page)return FX_EMPTY;
    if(page==&m->choices.page && !live(l)){*destination=ROOT_PAGE;return FX_OK;}
    if(page!=m->parent)return FX_EMPTY;
    FxResult result=refresh(m);if(result==FX_OK)result=fx_native_menu_restore(page);return result;
}
