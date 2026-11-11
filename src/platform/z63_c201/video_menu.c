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
#define MENU_COUNT 2u
#define TEXT_STRIDE 16u

struct FxZ63VideoMenu {
    FxNativeDescriptor descriptor;
    FxNativeRow rows[47];
    uintptr_t events[47],callbacks[5],original_callbacks[5];
    const FxNativeDescriptor *original;
    FxNativeEvent link[MENU_COUNT][FX_NATIVE_EVENTS];
    FxNativeMenu choices[MENU_COUNT];
    FxNativePage *parent;
    uint32_t refresh_calls,refresh_result;
    uintptr_t observed_page;
};
__attribute__((used,retain)) const uint32_t fx_z63_video_menu_layout[]={
    0x4658564du,2u,offsetof(FxZ63VideoQuality,menu),
    offsetof(FxZ63VideoMenu,refresh_calls),offsetof(FxZ63VideoMenu,refresh_result),
    offsetof(FxZ63VideoMenu,observed_page)};
extern void *fx_z63_current_page(void);

static void *allocate(uint32_t bytes) {
    return ((void *(*)(uint32_t,uint32_t))(uintptr_t)0x40d32d00u)(bytes,0u);
}
static FxZ63VideoMenuLease *lease(uint32_t index) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(!s)return 0;
    return atomic_load_explicit(index?&s->h265_menu_lease:&s->menu_lease,memory_order_acquire);
}
static int live(const FxZ63VideoMenuLease *l) {
    return l && atomic_load_explicit(&l->active,memory_order_acquire) && l->owner->phase==FX_OWNER_RUNNING;
}
static uint32_t allowed_index(uint32_t index) {
    if(!live(lease(index)))return 0u;
    uint32_t format=((uint32_t (*)(uint32_t))(uintptr_t)0x403ffcd0u)(0x06000f06u);
    return index?(format==2u || format==3u):format==4u;
}
static uint32_t allowed_prores(void *p){(void)p;return allowed_index(0u);}
static uint32_t allowed_h265(void *p){(void)p;return allowed_index(1u);}
static uint32_t noop(void *p){(void)p;return 1u;}

FxResult fx_z63_video_menu_bind(FxPlatformOwner *owner,uint64_t token,uint32_t control,uint32_t family) {
    if(!owner || !token || !control || (family!=FX_VIDEO_FAMILY_PRORES422 && family!=FX_VIDEO_FAMILY_H265))return FX_ARGUMENT;
    FxUiControl controls[FX_UI_CONTROLS];
    uint32_t count=0u,revision=0u,found=0u;
    FxResult result=fx_ui_snapshot(owner,controls,FX_UI_CONTROLS,&count,&revision);
    if(result!=FX_OK)return result;
    for(uint32_t i=0u;i<count;++i)
        if(controls[i].id==control && controls[i].kind==FX_UI_CHOICE && controls[i].option_count==5u)found=1u;
    if(!found)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(!s)return FX_STATE;
    uint32_t index=family==FX_VIDEO_FAMILY_H265;
    FxZ63VideoMenuLease *old=lease(index);
    if(live(old))return old->owner==owner && old->token==token && old->control==control?FX_OK:FX_BUSY;
    FxZ63VideoMenuLease *l=allocate(sizeof(*l));
    if(!l)return FX_BUDGET;
    *l=(FxZ63VideoMenuLease){.owner=owner,.token=token,.control=control,.family=family};
    atomic_init(&l->active,1u);
    atomic_store_explicit(index?&s->h265_menu_lease:&s->menu_lease,l,memory_order_release);
    return FX_OK;
}
void fx_z63_video_menu_unbind(FxPlatformOwner *owner,uint64_t token) {
    for(uint32_t i=0u;i<MENU_COUNT;++i) {
        FxZ63VideoMenuLease *l=lease(i);
        if(l && l->owner==owner && l->token==token)atomic_store_explicit(&l->active,0u,memory_order_release);
    }
}
static uint32_t choose(uint32_t value) {
    const FxNativePage *page=fx_z63_current_page();
    if(!page)return 0u;
    uint32_t id=page->identity>>16;
    if(id<FX_Z63_VIDEO_MENU_PAGE || id>=FX_Z63_VIDEO_MENU_PAGE+MENU_COUNT)return 0u;
    uint32_t index=id-FX_Z63_VIDEO_MENU_PAGE;
    FxZ63VideoMenuLease *l=lease(index);
    if(!allowed_index(index))return 0u;
    FxResult result=fx_z63_video_menu_select(l,value);
    if(result==FX_OK)fx_native_ui_refresh_owner(l->owner);
    return result==FX_OK;
}
static uint32_t stock(void *p){(void)p;return choose(0u);}
static uint32_t second(void *p){(void)p;return choose(1u);}
static uint32_t third(void *p){(void)p;return choose(2u);}
static uint32_t fourth(void *p){(void)p;return choose(3u);}
static uint32_t fifth(void *p){(void)p;return choose(4u);}
static const FxNativeTextProfile text_profile={(uintptr_t)fx_z63_current_page,0x40331b28u,0x4032b8bcu,
    0x404054a8u,0x404054e8u,0x40337910u,0x4032b3dcu,0x4dc0u,0x1c0u,0x118u,0x404056b0u,0u,0u};
static const FxNativeVisibilityProfile visibility={(uintptr_t)fx_z63_current_page,0x40331b28u,
    0x404054c8u,0x4032b3dcu,0x4032b8bcu,0x1c0u,0x4dc1u,0x4dc0u};

static const FxNativeLayoutProfile layout={(uintptr_t)fx_z63_current_page,0x403c0d9cu,0x403c0eacu,
    0x403c0ffcu,0x403c0e14u,0x403bf82cu,0x403bfaf0u,0x403c1290u,0x403bfd54u};

static FxResult refresh(FxZ63VideoMenu *m) {
    if(!m)return FX_EMPTY;
    ++m->refresh_calls;
    m->observed_page=(uintptr_t)fx_z63_current_page();
    if(m->observed_page!=(uintptr_t)m->parent){m->refresh_result=FX_EMPTY;return FX_EMPTY;}
    FxResult result=FX_OK;
    for(uint32_t i=0u;i<MENU_COUNT;++i) {
        FxZ63VideoMenuLease *l=lease(i);
        result=fx_native_row_visibility(&visibility,m->parent,ROOT_ROW+i,live(l));
        if(result!=FX_OK)break;
        result=fx_native_row_value_visibility(&visibility,m->parent,ROOT_ROW+i,live(l));
        if(result!=FX_OK)break;
        result=fx_native_row_arrow(&visibility,m->parent,ROOT_ROW+i,live(l));
        if(result!=FX_OK)break;
        FxVideoQualityStatus status={0};
        FxResult queried=fx_z63_video_menu_status(l,&status);
        uint32_t enabled=allowed_index(i) && queried==FX_OK && !status.fault;
        uint32_t base=fx_z63_ui_video_text_base()+i*TEXT_STRIDE;
        uint32_t value=enabled?(status.pending?base+6u:base+1u+status.requested):base+7u;
        result=fx_native_text_prepare(&text_profile,m->parent,ROOT_ROW+i,base,value,enabled,0);
        if(result!=FX_OK)break;
    }
    if(result==FX_OK)result=fx_native_row_reflow_limit(&layout,m->parent,47u);
    m->refresh_result=(uint32_t)result;
    return result;
}
static void deferred_refresh(FxZ63VideoMenu *m) {
    if(refresh(m)==FX_OK)return;
    for(uint32_t i=0u;i<MENU_COUNT;++i) {
        FxZ63VideoMenuLease *l=lease(i);
        if(live(l))fx_native_ui_refresh_owner(l->owner);
    }
}
static uint64_t root_open(void *window) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    FxZ63VideoMenu *m=s?s->menu:0;
    if(!m)return 1u;
    uint64_t result=((uint64_t (*)(void *))m->original_callbacks[0])(window);
    deferred_refresh(m);
    return result;
}
static uint64_t root_refresh(void *window) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    FxZ63VideoMenu *m=s?s->menu:0;
    if(!m)return 1u;
    uint64_t result=((uint64_t (*)(void *))m->original_callbacks[4])(window);
    deferred_refresh(m);
    return result;
}
static uint32_t choice_open(void *page){(void)page;fx_native_ui_capture_task();return 1u;}

FxNativePage *fx_z63_video_menu_parent(FxNativePage *page,const FxNativeEvent *navigation,const FxNativeRow *choice_row) {
    if(!choice_row || !page || page->identity!=((ROOT_PAGE<<16)|2u))return page;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(!s)return page;
    FxZ63VideoMenu *m=s->menu;
    if(!live(lease(0u)) && !live(lease(1u))) {
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
       source->header!=UINT64_C(0x43cb3758) || source->rows!=UINT64_C(0x43cb3868) ||
       source->events!=UINT64_C(0x43cb4028) || page->callbacks!=UINT64_C(0xa028f55e0))return page;
    const FxNativeRow *rows=(const void *)source->rows;
    if(rows[9].word[0]!=2185u)return page;
    uint32_t base=fx_z63_ui_video_text_base();
    if(fx_z63_menu_text_ensure(base+FX_Z63_VIDEO_MENU_TEXTS)!=FX_OK ||
       fx_z63_menu_text_style(base,FX_Z63_VIDEO_MENU_TEXTS,2185u)!=FX_OK)return page;
    m=allocate(sizeof(*m));
    if(!m)return page;
    memset(m,0,sizeof(*m));m->parent=page;m->original=source;m->descriptor=*source;
    memcpy(m->original_callbacks,(const void *)page->callbacks,sizeof(m->callbacks));
    memcpy(m->callbacks,m->original_callbacks,sizeof(m->callbacks));
    m->callbacks[0]=(uintptr_t)root_open;m->callbacks[4]=(uintptr_t)root_refresh;
    memcpy(m->rows,rows,10u*sizeof(*rows));
    memcpy(m->rows+12u,rows+10u,35u*sizeof(*rows));
    const uintptr_t *events=(const void *)source->events;
    memcpy(m->events,events,10u*sizeof(*events));
    memcpy(m->events+12u,events+10u,35u*sizeof(*events));
    uint32_t selects[4]={0x2b3u,0x2b8u,0x2ccu,0x2dbu};
    uintptr_t actions[5]={(uintptr_t)stock,(uintptr_t)second,(uintptr_t)third,(uintptr_t)fourth,(uintptr_t)fifth};
    uintptr_t conditions[MENU_COUNT]={(uintptr_t)allowed_prores,(uintptr_t)allowed_h265};
    for(uint32_t index=0u;index<MENU_COUNT;++index) {
        uint32_t text=base+index*TEXT_STRIDE,page_id=FX_Z63_VIDEO_MENU_PAGE+index;
        uint32_t row_id=CHOICE_ROW+index*16u;
        m->rows[10u+index]=*choice_row;
        m->rows[10u+index].word[4]|=0x41u;
        m->rows[10u+index].word[0]=text;
        m->rows[10u+index].word[2]=65535u;
        m->rows[10u+index].word[6]=ROOT_ROW+index;
        if(fx_native_menu_link(m->link[index],navigation,0x3f2u,selects,(uintptr_t)noop,page_id)!=FX_OK)return page;
        for(uint32_t i=0u;i<FX_NATIVE_EVENTS && m->link[index][i].event!=0x3f2u;++i)
            for(uint32_t k=0u;k<4u;++k)
                if(m->link[index][i].event==selects[k])m->link[index][i].condition=conditions[index];
        m->events[10u+index]=(uintptr_t)m->link[index];
        FxNativeMenuProfile profile={page,choice_row,navigation,0x3f2u,0x2abu,
            {0x2b3u,0x2b8u,0x2ccu,0x2dbu},0x712u,ROOT_PAGE};
        uintptr_t callbacks[5]={(uintptr_t)choice_open,(uintptr_t)noop,m->original_callbacks[2],(uintptr_t)noop,(uintptr_t)noop};
        FxNativeEntry entries[6];
        for(uint32_t i=0u;i<5u;++i)entries[i]=(FxNativeEntry){text+1u+i,row_id+i,0u,0u,actions[i],ROOT_PAGE};
        entries[5]=(FxNativeEntry){text+8u,row_id+5u,0u,0u,(uintptr_t)noop,ROOT_PAGE};
        FxNativeMenu *choices=&m->choices[index];
        if(fx_native_menu_build(choices,&profile,page_id,text,entries,6u,callbacks)!=FX_OK)return page;
        for(uint32_t row=0u;row<5u;++row)for(uint32_t event=0u;event<FX_NATIVE_EVENTS;++event) {
            if(choices->handlers[row][event].event==profile.terminal)break;
            for(uint32_t k=0u;k<4u;++k)if(choices->handlers[row][event].event==selects[k]) {
                choices->handlers[row][event].condition=actions[row];choices->handlers[row][event].callback=(uintptr_t)noop;
            }
        }
    }
    m->descriptor.rows=(uintptr_t)m->rows;m->descriptor.events=(uintptr_t)m->events;m->descriptor.count=47u;
    s->menu=m;page->callbacks=(uintptr_t)m->callbacks;
    atomic_store_explicit((_Atomic uintptr_t *)&page->descriptor,(uintptr_t)&m->descriptor,memory_order_release);
    return page;
}
int fx_z63_video_menu_visible(const FxNativePage *page) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    FxZ63VideoMenu *m=s?s->menu:0;
    return m && (page==m->parent || page==&m->choices[0].page || page==&m->choices[1].page);
}
FxNativePage *fx_z63_video_menu_page(uint32_t page) {
    if(page<FX_Z63_VIDEO_MENU_PAGE || page>=FX_Z63_VIDEO_MENU_PAGE+MENU_COUNT)return 0;
    uint32_t index=page-FX_Z63_VIDEO_MENU_PAGE;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    FxZ63VideoMenu *m=s?s->menu:0;
    FxVideoQualityStatus status={0};
    if(!m || !allowed_index(index) || fx_z63_video_menu_status(lease(index),&status)!=FX_OK)return 0;
    m->choices[index].page.selected=(uint16_t)(status.requested<=4u?status.requested:0u);
    return &m->choices[index].page;
}
int fx_z63_video_menu_text(uint32_t id,const uint16_t **out,uint32_t *bytes) {
    uint32_t base=fx_z63_ui_video_text_base();
    if(id<base || id>=base+MENU_COUNT*TEXT_STRIDE)return 0;
    uint32_t index=(id-base)/TEXT_STRIDE,offset=(id-base)%TEXT_STRIDE;
    static const uint16_t *const labels[MENU_COUNT][9]={
        {u"Video quality (ProRes)",u"Stock",u"HQ",u"Standard",u"LT",u"Proxy",u"Waiting",u"",u"Back"},
        {u"Video bitrate (H.265)",u"100%",u"60%",u"45%",u"30%",u"20%",u"Waiting",u"",u"Back"}};
    if(offset>=9u)return 0;
    *out=labels[index][offset];
    uint32_t length=0u;while((*out)[length])++length;
    *bytes=length*2u;return 1;
}
FxResult fx_z63_video_menu_flush(FxPlatformOwner *owner,FxNativePage *page,uint32_t *destination) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    FxZ63VideoMenu *m=s?s->menu:0;
    if(!m || !page)return FX_EMPTY;
    for(uint32_t i=0u;i<MENU_COUNT;++i) {
        FxZ63VideoMenuLease *l=lease(i);
        if(!l || l->owner!=owner)continue;
        if(page==&m->choices[i].page && !live(l)){*destination=ROOT_PAGE;return FX_OK;}
        if(page==m->parent) {
            FxResult result=refresh(m);
            return result==FX_OK?fx_native_menu_restore(page):result;
        }
    }
    return FX_EMPTY;
}
