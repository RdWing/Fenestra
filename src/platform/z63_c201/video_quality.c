/* C2.01 native admission fence. No card/NVRAM writes, encoder replacement or
 * live instruction mutation. Original firmware continuations are generated
 * from the exact supplied input and checked independently at build time. */
#include "video_quality.h"
#include "fenestra_memory.h"
#include "z63_video_assets.h"
#define FN(a,t) ((t)(uintptr_t)UINT64_C(a))
__attribute__((used,retain)) const uint32_t fx_z63_h265_layout[]={0x46584835u,1u,
    offsetof(FxZ63VideoQuality,h265),offsetof(FxZ63VideoQuality,ready),
    offsetof(FxVideoQualityPolicy,effective),offsetof(FxVideoQualityPolicy,registered),
    offsetof(FxVideoQualityPolicy,active)};
static uint32_t native_idle(void) {
    if(*FN(0xa048bb044,volatile uint32_t *) || *FN(0xa03324ce0,volatile uint32_t *) ||
       *FN(0xa03324dc8,volatile uint32_t *))return 0u;
    uint32_t state=*FN(0xa03d42100,volatile uint32_t *),kind=*FN(0xa03d42108,volatile uint32_t *);
    return (state==2u && kind!=12u) || (!state && !kind);
}
static int lock(FxZ63VideoQuality *s) {
    if(!s || !atomic_load_explicit(&s->ready,memory_order_acquire))return 0;
    if(FN(0x40d32f74,uint32_t (*)(void *))(s->mutex)==1u)return 1;
    return 0;
}
static void unlock(FxZ63VideoQuality *s){FN(0x40d32f60,void (*)(void *))(s->mutex);}
void fx_z63_video_init(FxZ63VideoQuality *s) {
    fx_video_quality_init(&s->policy);fx_video_quality_init(&s->raw);
    fx_video_quality_init(&s->h265);atomic_init(&s->ready,0u);atomic_init(&s->playback,0u);
    atomic_init(&s->menu_lease,0);s->menu=0;
    FN(0x40d32e64,void (*)(void *,const char *))(s->mutex,"FXVIDEO");
    if(FN(0x40d32f98,uint32_t (*)(void *,uint32_t))(s->mutex,0u)!=1u){s->policy.fault=1u;return;}
    unlock(s);atomic_store_explicit(&s->ready,1u,memory_order_release);
}
static FxZ63VideoQuality *enter(uint32_t domain,uint32_t acknowledge) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(s && !lock(s)) { /* No untracked native admission may look idle. */
        atomic_store_explicit(&s->policy.fault,1u,memory_order_release);atomic_store(&s->raw.fault,1u);atomic_store(&s->h265.fault,1u);return 0;
    }
    if(s){
        if(atomic_load(&s->policy.fault)){
            atomic_store(&s->raw.fault,1u);atomic_store(&s->h265.fault,1u);
        }
        uint32_t idle=native_idle();
        fx_video_quality_enter(&s->policy,domain,acknowledge,idle);
        fx_video_quality_enter(&s->raw,domain,acknowledge,idle);
        fx_video_quality_enter(&s->h265,domain,acknowledge,idle);
        unlock(s);
    }
    return s;
}
static void leave(FxZ63VideoQuality *s,uint32_t domain) {
    if(!s)return;
    if(!lock(s)){atomic_store_explicit(&s->policy.fault,1u,memory_order_release);atomic_store(&s->raw.fault,1u);atomic_store(&s->h265.fault,1u);return;}
    if(atomic_load(&s->policy.fault)){
        atomic_store(&s->raw.fault,1u);atomic_store(&s->h265.fault,1u);
    }
    uint32_t idle=native_idle();
    fx_video_quality_leave(&s->policy,domain,idle);
    fx_video_quality_leave(&s->raw,domain,idle);
    fx_video_quality_leave(&s->h265,domain,idle);
    unlock(s);
}
static uint64_t registration(void *object,uintptr_t callback,uint32_t mask,void *config,
    uint32_t domain,uintptr_t expected_object,uintptr_t expected_callback,uint32_t expected_mask) {
    FxZ63VideoQuality *s=fx_z63_menu_prepare_video();
    if(s && ((uintptr_t)object!=expected_object || callback!=expected_callback || mask!=expected_mask))
        atomic_store_explicit(&s->policy.fault,1u,memory_order_release);
    s=enter(domain,1u);
    uint64_t result=FN(0x40c00204,uint64_t (*)(void *,uintptr_t,uint32_t,void *))(object,callback,mask,config);
    leave(s,domain);return result;
}
uint64_t fx_z63_video_register_movie(void *object,uintptr_t callback,uint32_t mask,void *config) {
    return registration(object,callback,mask,config,0u,UINT64_C(0xa03324b68),UINT64_C(0x40d22770),0x1fffu);
}
uint64_t fx_z63_video_register_capture(void *object,uintptr_t callback,uint32_t mask,void *config) {
    return registration(object,callback,mask,config,1u,UINT64_C(0xa048baf98),UINT64_C(0x40755a54),0xf1ffffffu);
}
extern uint64_t fx_z63_video_movie_original(uint32_t);
extern uint64_t fx_z63_video_capture_original(uint32_t);
extern uint32_t fx_z63_video_drain_original(void),fx_z63_video_cancel_original(void);
extern uint32_t fx_z63_video_configure_original(void *);
uint64_t fx_z63_video_movie(uint32_t flags) {
    FxZ63VideoQuality *s=enter(0u,1u);uint64_t r=fx_z63_video_movie_original(flags);leave(s,0u);return r;
}
uint64_t fx_z63_video_capture(uint32_t flags) {
    FxZ63VideoQuality *s=enter(1u,1u);uint64_t r=fx_z63_video_capture_original(flags);leave(s,1u);return r;
}
uint32_t fx_z63_video_drain(void) {
    FxZ63VideoQuality *s=enter(1u,0u);uint32_t r=fx_z63_video_drain_original();leave(s,1u);return r;
}
uint32_t fx_z63_video_cancel(void) {
    FxZ63VideoQuality *s=enter(1u,0u);uint32_t r=fx_z63_video_cancel_original();leave(s,1u);return r;
}
uint32_t fx_z63_video_configure(void *q) {
    FxZ63VideoQuality *s=enter(1u,0u);uint32_t r=fx_z63_video_configure_original(q);leave(s,1u);return r;
}
uint32_t fx_z63_video_code(void) {
    FxZ63VideoQuality *s=fx_z63_menu_video();
    return s?atomic_load_explicit(&s->policy.effective,memory_order_acquire):0u;
}
extern void fx_z63_video_rate_original(const void *,void *);
void fx_z63_video_rate(const void *input,void *out) {
    uint32_t code=fx_z63_video_code();if(!code){fx_z63_video_rate_original(input,out);return;}
    uint32_t index=0u;FN(0x40d22400,void (*)(const void *,uint32_t *))(input,&index);
    if(code>4u || index>=12u){fx_z63_video_rate_original(input,out);return;}
    memcpy(out,fx_z63_video_rates[code-1u]+index*24u,24u);
}
uintptr_t fx_z63_video_template(void) {
    uint32_t code=fx_z63_video_code();
    return code && code<=4u?(uintptr_t)fx_z63_video_templates[code-1u]:UINT64_C(0x42b7145a);
}
uintptr_t fx_z63_video_shoot(void) {
    uint32_t code=fx_z63_video_code();
    return code && code<=4u?(uintptr_t)fx_z63_video_shoot_tables[code-1u]:UINT64_C(0x4408a060);
}
uint32_t fx_z63_video_parse(uint32_t fourcc) {
    static const uint32_t codes[4]={0x61706368u,0x6170636eu,0x61706373u,0x6170636fu};
    FxZ63VideoQuality *s=fx_z63_menu_video();uint32_t enabled=fx_z63_video_code();
    for(uint32_t q=0u;q<(enabled?4u:1u);++q)if(fourcc==codes[q]) {
        if(s)atomic_store_explicit(&s->playback,q,memory_order_release);return 1u;
    }
    return 0u;
}
void fx_z63_video_play(uint8_t *out) {
    static const char labels[4][14]={"ProRes 422 HQ","ProRes 422","ProRes 422 LT","ProRes Proxy"};
    FxZ63VideoQuality *s=fx_z63_menu_video();
    uint32_t q=s && fx_z63_video_code()?atomic_load_explicit(&s->playback,memory_order_acquire):0u;
    memcpy(out,labels[q<4u?q:0u],14u);
}
FxResult fx_z63_video_resource(void *context,uint32_t op,const FxNamedBinding *binding,FxPlatformOwner *owner,
    uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)binding;
    if(!owner || !cookie || !token)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s)return FX_STATE;
    if(op==FX_RESOURCE_ATTACH){
        if(!atomic_load_explicit(&s->ready,memory_order_acquire))return FX_STATE;
        *cookie=token;return FX_OK;
    }
    if(*cookie!=token)return FX_STALE;
    if(!lock(s))return FX_BUSY;
    uint32_t idle=native_idle();FxResult result=FX_ARGUMENT;
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC) {
        fx_z63_video_menu_unbind(owner,token);
        result=fx_video_quality_release(&s->policy,token,idle);
        if(result==FX_OK && op==FX_RESOURCE_DETACH)*cookie=0u;
    } else if(op==FX_RESOURCE_CALL && q && a) {
        fx_video_quality_commit(&s->policy,idle);
        if(q->arg[3])result=FX_ARGUMENT;
        else if(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection)) {
            FxVideoQualitySelection choice;memcpy(&choice,q->data,sizeof(choice));
            if(choice.abi==FX_VIDEO_QUALITY_ABI && choice.bytes==sizeof(choice) && choice.family==FX_VIDEO_FAMILY_PRORES422)
                result=choice.choice && (s->raw.requested || atomic_load(&s->raw.effective))?FX_BUSY:fx_video_quality_select(&s->policy,token,choice.choice,idle);
        } else if(q->arg[2]==FX_VIDEO_QUALITY_MENU && q->bytes==sizeof(FxVideoQualityMenu)) {
            FxVideoQualityMenu menu;memcpy(&menu,q->data,sizeof(menu));
            if(menu.abi==1u && menu.bytes==sizeof(menu) && !menu.reserved)
                result=fx_z63_video_menu_bind(owner,token,menu.control);
        } else if(!q->bytes && q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
            FxVideoQualityInfo info={1u,sizeof(info),FX_VIDEO_FAMILY_PRORES422,31u,
                FX_VIDEO_QUALITY_SESSION_ONLY|FX_VIDEO_QUALITY_EXPERIMENTAL|FX_VIDEO_QUALITY_NATIVE_MENU,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(!q->bytes && q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
            FxVideoQualityPolicy *p=&s->policy;uint32_t effective=atomic_load_explicit(&p->effective,memory_order_acquire);
            FxVideoQualityStatus status={1u,sizeof(status),FX_VIDEO_FAMILY_PRORES422,p->requested,effective,
                p->registered==3u && idle && !p->active[0] && !p->active[1] && !p->fault,
                p->active[0],p->active[1],p->requested!=effective || p->retiring,p->fault,p->transitions,0u};
            memcpy(a->data,&status,sizeof(status));a->bytes=sizeof(status);result=FX_OK;
        }
    }
    unlock(s);return result;
}

FxResult fx_z63_video_menu_status(FxZ63VideoMenuLease *lease,FxVideoQualityStatus *out) {
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s || !lease || !out)return FX_ARGUMENT;
    if(!lock(s))return FX_BUSY;
    FxResult result=FX_STATE;
    if(atomic_load(&s->menu_lease)==lease && atomic_load(&lease->active) && lease->owner->phase==FX_OWNER_RUNNING) {
        fx_video_quality_commit(&s->policy,native_idle());
        FxVideoQualityPolicy *p=&s->policy;
        *out=(FxVideoQualityStatus){1u,sizeof(*out),1u,p->requested,atomic_load(&p->effective),0u,
            p->active[0],p->active[1],p->requested!=atomic_load(&p->effective) || p->retiring,atomic_load(&p->fault),p->transitions,0u};
        result=FX_OK;
    }
    unlock(s);return result;
}
FxResult fx_z63_video_menu_select(FxZ63VideoMenuLease *lease,uint32_t choice) {
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s || !lease)return FX_ARGUMENT;
    if(!lock(s))return FX_BUSY;
    FxResult result=FX_STATE;
    if(atomic_load(&s->menu_lease)==lease && atomic_load(&lease->active) && lease->owner->phase==FX_OWNER_RUNNING)
        result=choice && (s->raw.requested || atomic_load(&s->raw.effective))?FX_BUSY:fx_video_quality_select(&s->policy,lease->token,choice,native_idle());
    unlock(s);return result;
}

/* RAW compatibility uses the same registration, admission mutex and active
 * counters as ProRes. No feature changes the encoder or capture gain. */
#include "fenestra_video_color.h"
FxResult fx_z63_raw_resource(void *context,uint32_t op,const FxNamedBinding *binding,
    FxPlatformOwner *owner,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)binding;
    if(!owner || !token || !cookie)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s)return FX_STATE;
    if(op==FX_RESOURCE_ATTACH){if(!atomic_load_explicit(&s->ready,memory_order_acquire))return FX_STATE;*cookie=token;return FX_OK;}
    if(*cookie!=token)return FX_STALE;
    if(!lock(s))return FX_BUSY;
    uint32_t idle=native_idle();FxVideoQualityPolicy *p=&s->raw;
    if(atomic_load(&s->policy.fault))atomic_store(&p->fault,1u);
    fx_video_quality_commit(p,idle);FxResult result=FX_ARGUMENT;
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC) {
        result=fx_video_quality_release(p,token,idle);
        if(result==FX_OK)*cookie=0u;
    } else if(op==FX_RESOURCE_CALL && q && a && !q->arg[3]) {
        if(q->arg[2]==FX_VIDEO_QUALITY_QUERY && !q->bytes) {
            FxVideoQualityInfo info={1u,sizeof(info),FX_VIDEO_FAMILY_RAW,3u,
                FX_VIDEO_QUALITY_SESSION_ONLY|FX_VIDEO_QUALITY_EXPERIMENTAL,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS && !q->bytes) {
            FxVideoQualityStatus info={1u,sizeof(info),FX_VIDEO_FAMILY_RAW,p->requested,
                atomic_load(&p->effective),p->registered==3u && idle && !p->active[0] && !p->active[1] && !p->fault,
                p->active[0],p->active[1],p->requested!=atomic_load(&p->effective)||p->retiring,
                atomic_load(&p->fault),p->transitions,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection)) {
            FxVideoQualitySelection sel;memcpy(&sel,q->data,sizeof(sel));
            if(sel.abi==1u && sel.bytes==sizeof(sel) && sel.family==FX_VIDEO_FAMILY_RAW && sel.choice<=1u) {
                if(sel.choice && FN(0x403ffcd0,uint32_t (*)(uint32_t))(UINT32_C(0x06000f06))!=6u)result=FX_STATE;
                else if(sel.choice && (s->policy.requested || atomic_load(&s->policy.effective)))result=FX_BUSY;
                else result=fx_video_quality_select(p,token,sel.choice,idle);
            }
        } else if(q->arg[2]==FX_VIDEO_QUERY_PATH && q->bytes==4u) {
            uint32_t path;memcpy(&path,q->data,4u);
            if(path<FX_VIDEO_PATH_COUNT) {
                FxVideoPathInfo info={1u,sizeof(info),path,path==FX_VIDEO_PATH_NRAW,
                    path==FX_VIDEO_PATH_NRAW?FX_VIDEO_REASON_NONE:FX_VIDEO_REASON_WRITER_JOIN,1u,0u,0u};
                memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
            }
        } else result=FX_CAPABILITY;
    }
    unlock(s);return result;
}
uint32_t fx_z63_raw_code(void) {
    FxZ63VideoQuality *s=fx_z63_menu_video();return s?atomic_load_explicit(&s->raw.effective,memory_order_acquire):0u;
}
extern uint32_t fx_z63_video_raw_matrix_original(void *,void *);
uint32_t fx_z63_raw_matrix(void *context,void *out) {
    if(!fx_z63_raw_code())return fx_z63_video_raw_matrix_original(context,out);
    memcpy(out,fx_z63_raw_matrix_bytes,sizeof(fx_z63_raw_matrix_bytes));return sizeof(fx_z63_raw_matrix_bytes);
}
const char *fx_z63_raw_extension(void) {
    return fx_z63_raw_code()?"R3D":(const char *)(uintptr_t)UINT64_C(0x442763dc);
}
uintptr_t fx_z63_raw_template_copy(void *out,const void *source,uint32_t bytes) {
    if(fx_z63_raw_code() && bytes==86u) {
        if((uintptr_t)source==UINT64_C(0x42b7153a))source=fx_z63_raw_templates[0];
        else if((uintptr_t)source==UINT64_C(0x42b71590))source=fx_z63_raw_templates[1];
    }
    return FN(0x40ce5c60,uintptr_t (*)(void *,const void *,uint32_t))(out,source,bytes);
}

FxResult fx_z63_h265_resource(void *context,uint32_t op,const FxNamedBinding *binding,
    FxPlatformOwner *owner,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)binding;
    if(!owner || !cookie || !token)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(!s || !atomic_load(&s->ready))return FX_STATE;
    if(op==FX_RESOURCE_ATTACH){*cookie=token;return FX_OK;}
    if(*cookie!=token)return FX_STALE;
    if(!lock(s))return FX_BUSY;
    FxVideoQualityPolicy *p=&s->h265;
    uint32_t idle=native_idle();
    FxResult result=FX_ARGUMENT;
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC) {
        result=fx_video_quality_release(p,token,idle);
        if(result==FX_OK && op==FX_RESOURCE_DETACH)*cookie=0u;
    } else if(op==FX_RESOURCE_CALL && q && a && !q->arg[3]) {
        fx_video_quality_commit(p,idle);
        if(q->arg[2]==FX_VIDEO_QUALITY_QUERY && !q->bytes) {
            FxVideoQualityInfo info={1u,sizeof(info),FX_VIDEO_FAMILY_H265,31u,
                FX_VIDEO_QUALITY_SESSION_ONLY|FX_VIDEO_QUALITY_EXPERIMENTAL,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS && !q->bytes) {
            uint32_t effective=atomic_load(&p->effective), fault=atomic_load(&p->fault);
            FxVideoQualityStatus info={1u,sizeof(info),FX_VIDEO_FAMILY_H265,p->requested,effective,
                p->registered==3u && idle && !p->active[0] && !p->active[1] && !fault,
                p->active[0],p->active[1],p->requested!=effective || p->retiring,fault,p->transitions,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection)) {
            FxVideoQualitySelection choice;
            memcpy(&choice,q->data,sizeof(choice));
            if(choice.abi==1u && choice.bytes==sizeof(choice) && choice.family==FX_VIDEO_FAMILY_H265 && choice.choice<=4u) {
                uint32_t type=FN(0x403ffcd0,uint32_t (*)(uint32_t))(UINT32_C(0x06000f06));
                result=choice.choice && type!=2u && type!=3u?FX_STATE:fx_video_quality_select(p,token,choice.choice,idle);
            }
        } else result=FX_CAPABILITY;
    }
    unlock(s);return result;
}

void *fx_z63_h265_copy(void *out,const void *source,uint64_t bytes,uint64_t index) {
    void *result=FN(0x4163b5c0,void *(*)(void *,const void *,uint64_t))(out,source,bytes);
    /* The original selector chose this row. Restrict the adjustment to the
     * pinned H.265 table and only the six supported width/depth combinations. */
    if(bytes!=36u || index>=61u || out==source ||
       (uintptr_t)source!=UINT64_C(0x42ac02fc)+36u*index)return result;
    uint32_t codec, format, rate;
    memcpy(&codec,source,4u);
    memcpy(&format,(const uint8_t *)source+4u,4u);
    uint32_t width=format>>16, depth=format&65535u;
    if(codec!=1u || (depth!=8u && depth!=10u) ||
       (width!=1920u && width!=3840u && width!=5376u))return result;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    uint32_t tier=s?atomic_load_explicit(&s->h265.effective,memory_order_acquire):0u;
    static const uint32_t percent[]={100u,60u,45u,30u,20u};
    if(tier && tier<sizeof(percent)/sizeof(percent[0])) {
        memcpy(&rate,(const uint8_t *)source+28u,4u);
        rate=(uint32_t)((uint64_t)rate*percent[tier]/100u);
        memcpy((uint8_t *)out+28u,&rate,4u);
    }
    return result;
}
