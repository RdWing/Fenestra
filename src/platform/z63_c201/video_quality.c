/* C2.01 native admission fence. Persistent H.265 choices use the original
 * settings worker; no direct flash writer or encoder replacement is supplied.
 * Original continuations are generated from the checked input image. */
#include "video_quality.h"
#include "fenestra_memory.h"
#include "fenestra_video_settings.h"
#include "z63_video_assets.h"
#define FN(a,t) ((t)(uintptr_t)UINT64_C(a))
__attribute__((used,retain)) const uint32_t fx_z63_h265_layout[]={0x46584835u,2u,
    offsetof(FxZ63VideoQuality,h265),offsetof(FxZ63VideoQuality,ready),
    offsetof(FxVideoQualityPolicy,effective),offsetof(FxVideoQualityPolicy,registered),
    offsetof(FxVideoQualityPolicy,active),offsetof(FxPlatformOwner,phase),
    offsetof(FxZ63VideoQuality,settings_busy)};
static _Atomic uint32_t *settings_word(void);
static FxResult persisted_select(FxPlatformOwner *,uint64_t,uint32_t,FxZ63VideoMenuLease *,uint32_t);
static int saved_choice(uint32_t word,uint32_t family,uint32_t *choice) {
    if(family==FX_VIDEO_FAMILY_H265)return fx_h265_settings_read(word,choice);
    uint32_t grade;
    if(!fx_prores_settings_read(word,&grade))return 0;
    /* Stock and HQ share stored grade zero. Restore its Stock alias. */
    *choice=grade?grade+1u:0u;
    return 1;
}
static uint32_t native_idle(void) {
    if(*FN(0xa048bb044,volatile uint32_t *) || *FN(0xa03324ce0,volatile uint32_t *) ||
       *FN(0xa03324dc8,volatile uint32_t *))return 0u;
    uint32_t state=*FN(0xa03d42100,volatile uint32_t *),kind=*FN(0xa03d42108,volatile uint32_t *);
    return (state==2u && kind!=12u) || (!state && !kind);
}
/* Called only with our mutex held, after the complete context was published.
 * A pre-publication callback must have returned before its task can wait on
 * the dispatcher flag. New callbacks cannot pass enter() while we hold this
 * mutex. Do not infer quiescence from a registered pointer or a generic WAIT. */
__attribute__((used,retain)) const uint32_t fx_z63_late_join_layout[]={0x464a4e31u,1u,
    offsetof(FxZ63VideoQuality,ready),offsetof(FxZ63VideoQuality,late_join),
    offsetof(FxZ63VideoQuality,policy),offsetof(FxZ63VideoQuality,raw),offsetof(FxZ63VideoQuality,h265),
    offsetof(FxVideoQualityPolicy,registered),offsetof(FxVideoQualityPolicy,active),offsetof(FxVideoQualityPolicy,fault)};
__attribute__((noinline)) static void join_waiting_domains(FxZ63VideoQuality *s) {
    if(!atomic_load_explicit(&s->late_join,memory_order_acquire) || s->policy.fault || !native_idle())return;
    static const uintptr_t objects[2]={UINT64_C(0xa03324b68),UINT64_C(0xa048baf98)};
    static const uintptr_t callbacks[2]={UINT64_C(0x40d22770),UINT64_C(0x40755a54)};
    static const uint32_t masks[2]={0x1fffu,0xf1ffffffu};
    for(uint32_t domain=0u;domain<2u;++domain) {
        uint32_t bit=1u<<domain;
        if((s->policy.registered&bit) || s->policy.active[domain])continue;
        const volatile uint8_t *object=(const volatile uint8_t *)objects[domain];
        int32_t id=*(const volatile int32_t *)object;
        int32_t flag=*(const volatile int32_t *)(object+0x38);
        if(id<=0 || flag<=0 || *(const volatile uintptr_t *)(object+8)!=UINT64_C(0x40c0025c) ||
           *(const volatile uintptr_t *)(object+0x48)!=callbacks[domain] ||
           *(const volatile uint32_t *)(object+0x50)!=masks[domain])continue;
        _Alignas(8) uint32_t info[20]={0};
        if(FN(0x4018c8cc,int32_t (*)(int32_t,void *))(id,info) ||
           info[0]!=4u || info[3]!=8u || info[4]!=(uint32_t)flag ||
           id!=*(const volatile int32_t *)object || flag!=*(const volatile int32_t *)(object+0x38) ||
           *(const volatile uintptr_t *)(object+8)!=UINT64_C(0x40c0025c) ||
           *(const volatile uintptr_t *)(object+0x48)!=callbacks[domain] ||
           *(const volatile uint32_t *)(object+0x50)!=masks[domain] || !native_idle())continue;
        s->policy.registered|=bit;s->raw.registered|=bit;s->h265.registered|=bit;
    }
}
static int lock(FxZ63VideoQuality *s) {
    if(!s || !atomic_load_explicit(&s->ready,memory_order_acquire))return 0;
    if(FN(0x40d32f74,uint32_t (*)(void *))(s->mutex)==1u){join_waiting_domains(s);return 1;}
    return 0;
}
static void unlock(FxZ63VideoQuality *s){FN(0x40d32f60,void (*)(void *))(s->mutex);}
int fx_z63_video_quiescent(FxZ63VideoQuality *s) {
    if(!lock(s))return 0;
    FxVideoQualityPolicy *policies[]={&s->policy,&s->raw,&s->h265};
    int ready=!atomic_load(&s->settings_busy);
    for(uint32_t i=0;i<3u;++i) {
        FxVideoQualityPolicy *p=policies[i];
        if(p->owner || p->requested || atomic_load(&p->effective) || p->active[0] || p->active[1] || p->retiring)ready=0;
    }
    unlock(s);return ready;
}
void fx_z63_video_init(FxZ63VideoQuality *s) {
    fx_video_quality_init(&s->policy);fx_video_quality_init(&s->raw);
    fx_video_quality_init(&s->h265);atomic_init(&s->ready,0u);atomic_init(&s->playback,0u);
    atomic_init(&s->menu_lease,0);atomic_init(&s->h265_menu_lease,0);
    atomic_init(&s->settings_busy,0u);atomic_init(&s->save_generation,0u);
    atomic_init(&s->save_sequence,0u);atomic_init(&s->save_result,0u);s->menu=0;
    s->prores_owner=0;s->h265_owner=0;
    atomic_init(&s->late_join,0u);
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
    /* Startup registration must not allocate Fenestra state. After the stock
     * completion event, late initialization publishes the context. Both native
     * callback domains must subsequently acknowledge it before selection. */
    FxZ63VideoQuality *s=fx_z63_menu_video();
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
        if(!lock(s))return FX_BUSY;
        if(atomic_load(&s->settings_busy)){unlock(s);return FX_BUSY;}
        uint32_t choice;
        if(!s->policy.owner && saved_choice(atomic_load(settings_word()),FX_VIDEO_FAMILY_PRORES422,&choice)) {
            if(choice && (s->raw.requested || atomic_load(&s->raw.effective))){unlock(s);return FX_BUSY;}
            (void)fx_video_quality_select(&s->policy,token,choice,native_idle());
        }
        if(s->policy.owner==token)s->prores_owner=owner;
        *cookie=token;unlock(s);return FX_OK;
    }
    if(*cookie!=token)return FX_STALE;
    if(op==FX_RESOURCE_CALL && q && a && !q->arg[3] && q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection)) {
        FxVideoQualitySelection choice;memcpy(&choice,q->data,sizeof(choice));
        if(choice.abi!=FX_VIDEO_QUALITY_ABI || choice.bytes!=sizeof(choice) || choice.family!=FX_VIDEO_FAMILY_PRORES422)return FX_ARGUMENT;
        return persisted_select(owner,token,choice.choice,0,FX_VIDEO_FAMILY_PRORES422);
    }
    if(!lock(s))return FX_BUSY;
    uint32_t idle=native_idle();FxResult result=FX_ARGUMENT;
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC) {
        fx_z63_video_menu_unbind(owner,token);
        result=atomic_load(&s->settings_busy)?FX_BUSY:fx_video_quality_release(&s->policy,token,idle);
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
                result=fx_z63_video_menu_bind(owner,token,menu.control,FX_VIDEO_FAMILY_PRORES422);
        } else if(!q->bytes && q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
            FxVideoQualityInfo info={1u,sizeof(info),FX_VIDEO_FAMILY_PRORES422,31u,
                FX_VIDEO_QUALITY_PERSISTENT|FX_VIDEO_QUALITY_EXPERIMENTAL|FX_VIDEO_QUALITY_NATIVE_MENU,0u};
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
    if(atomic_load(lease->family==FX_VIDEO_FAMILY_H265?&s->h265_menu_lease:&s->menu_lease)==lease && atomic_load(&lease->active) && lease->owner->phase==FX_OWNER_RUNNING) {
        FxVideoQualityPolicy *p=lease->family==FX_VIDEO_FAMILY_H265?&s->h265:&s->policy;
        fx_video_quality_commit(p,native_idle());
        *out=(FxVideoQualityStatus){1u,sizeof(*out),lease->family,p->requested,atomic_load(&p->effective),0u,
            p->active[0],p->active[1],p->requested!=atomic_load(&p->effective) || p->retiring,atomic_load(&p->fault),p->transitions,0u};
        result=FX_OK;
    }
    unlock(s);return result;
}
FxResult fx_z63_video_menu_select(FxZ63VideoMenuLease *lease,uint32_t choice) {
    FxZ63VideoQuality *s=fx_z63_menu_video();if(!s || !lease)return FX_ARGUMENT;
    if(lease->family==FX_VIDEO_FAMILY_H265)return fx_z63_h265_select(lease->owner,lease->token,choice,lease);
    return persisted_select(lease->owner,lease->token,choice,lease,FX_VIDEO_FAMILY_PRORES422);
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
                if(sel.choice && atomic_load(&s->settings_busy))result=FX_BUSY;
                else if(sel.choice && FN(0x403ffcd0,uint32_t (*)(uint32_t))(UINT32_C(0x06000f06))!=6u)result=FX_STATE;
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

#define SETTINGS_WORD UINT64_C(0xa03f0eef4)
static _Atomic uint32_t *settings_word(void) {
    return (_Atomic uint32_t *)(uintptr_t)SETTINGS_WORD;
}

static int replace_settings(uint32_t expected, uint32_t desired) {
    for (uint32_t attempt = 0; attempt < 16u; ++attempt) {
        uint32_t actual = atomic_load_explicit(settings_word(),memory_order_acquire);
        if ((actual >> 8) != (expected >> 8)) return 0;
        uint32_t next = (actual & 255u) | (desired & UINT32_C(0xffffff00));
        if (atomic_compare_exchange_strong_explicit(settings_word(),&actual,next,
                memory_order_acq_rel,memory_order_acquire)) return 1;
    }
    return 0;
}

uint32_t fx_z63_h265_save_result(uint32_t mode) {
    FxZ63VideoQuality *s = fx_z63_menu_video();
    uint32_t generation = s ? atomic_load_explicit(&s->save_generation,memory_order_acquire) : 0u;
    uint32_t result = FN(0x41003538,uint32_t (*)(uint32_t))(mode);
    if (generation && atomic_load_explicit(&s->save_generation,memory_order_acquire) == generation) {
        atomic_store_explicit(&s->save_result,result,memory_order_relaxed);
        atomic_fetch_add_explicit(&s->save_sequence,1u,memory_order_release);
    }
    return result;
}

FxResult fx_z63_h265_select(FxPlatformOwner *owner,uint64_t token,uint32_t choice,
                          FxZ63VideoMenuLease *menu_lease) {
    return persisted_select(owner,token,choice,menu_lease,FX_VIDEO_FAMILY_H265);
}
static FxResult persisted_select(FxPlatformOwner *owner,uint64_t token,uint32_t choice,
                                FxZ63VideoMenuLease *menu_lease,uint32_t family) {
    if (!owner || !token || choice>4u) return FX_ARGUMENT;
    uint32_t h265=family==FX_VIDEO_FAMILY_H265;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if (!lock(s)) return FX_BUSY;
    FxVideoQualityPolicy *policy=h265?&s->h265:&s->policy;
    FxResult refused=FX_STATE;
    if (atomic_load(&policy->fault) || policy->retiring || owner->phase!=FX_OWNER_RUNNING)
        goto refuse;
    if (menu_lease && (atomic_load(h265?&s->h265_menu_lease:&s->menu_lease)!=menu_lease || !atomic_load(&menu_lease->active)))
        goto refuse;
    if ((policy->owner && policy->owner!=token) || atomic_load(&s->settings_busy)) {
        refused=FX_BUSY;goto refuse;
    }
    uint32_t type=FN(0x403ffcd0,uint32_t (*)(uint32_t))(UINT32_C(0x06000f06));
    if (h265 && choice && type!=2u && type!=3u) goto refuse;
    if (!h265 && choice && (s->raw.requested || atomic_load(&s->raw.effective))) {
        refused=FX_BUSY;goto refuse;
    }
    if (policy->registered!=3u || !native_idle() || policy->active[0] || policy->active[1]) {
        refused=FX_BUSY;goto refuse;
    }
    uint32_t prior_choice=policy->requested;
    uint32_t prior=atomic_load_explicit(settings_word(),memory_order_acquire),next;
    if (!(h265?fx_h265_settings_write(prior,choice,&next):fx_prores_settings_write(prior,choice?choice-1u:0u,&next))) goto refuse;
    uint32_t sequence=atomic_load_explicit(&s->save_sequence,memory_order_acquire);
    if (sequence==UINT32_MAX || !replace_settings(prior,next)) goto refuse;
    if(h265)s->h265_owner=owner;else s->prores_owner=owner;
    atomic_store(&s->settings_busy,1u);
    atomic_store_explicit(&s->save_generation,sequence+1u,memory_order_release);
    unlock(s);

    /* The original settings worker owns the flash operation. Its callback
     * observes this generation before entering the original save routine. */
    FN(0x41003bc0,void (*)(void))();
    atomic_store_explicit(&s->save_generation,0u,memory_order_release);
    uint32_t observed=atomic_load_explicit(settings_word(),memory_order_acquire);
    int saved=atomic_load_explicit(&s->save_sequence,memory_order_acquire)==sequence+1u &&
        atomic_load(&s->save_result)==1u && (observed>>8)==(next>>8);
    int owned=1;
    if (!saved && !replace_settings(next,prior)) {
        uint32_t tier;
        observed=atomic_load_explicit(settings_word(),memory_order_acquire);
        owned=(observed>>8)!=(next>>8) && saved_choice(observed,family,&tier);
    }
    if (!lock(s)) {
        atomic_store(&policy->fault,1u);
        atomic_store_explicit(&s->settings_busy,0u,memory_order_release);
        return FX_STATE;
    }
    FxResult result=FX_STATE;
    if (!owned) atomic_store(&policy->fault,1u);
    if (saved) {
        result=fx_video_quality_select(policy,token,choice,native_idle());
        if (owner->phase!=FX_OWNER_RUNNING)
            (void)fx_video_quality_release(policy,token,native_idle());
    } else if (owned) {
        uint32_t tier;
        uint32_t restored=atomic_load(settings_word());
        if (saved_choice(restored,family,&tier)) {
            if((restored>>8)==(prior>>8))tier=prior_choice;
            (void)fx_video_quality_select(policy,token,tier,native_idle());
            /* A reset/recall can replace both families in the shared record. */
            uint32_t other_family=h265?FX_VIDEO_FAMILY_PRORES422:FX_VIDEO_FAMILY_H265;
            FxVideoQualityPolicy *other=h265?&s->policy:&s->h265;
            FxPlatformOwner *other_owner=h265?s->prores_owner:s->h265_owner;
            uint32_t before_other,after_other;
            if(other->owner && other_owner && other_owner->phase==FX_OWNER_RUNNING && saved_choice(prior,other_family,&before_other) &&
               saved_choice(restored,other_family,&after_other) && before_other!=after_other) {
                if(h265 && after_other && (s->raw.requested || atomic_load(&s->raw.effective)))
                    atomic_store(&other->fault,1u);
                else (void)fx_video_quality_select(other,other->owner,after_other,native_idle());
            }
        }
    }
    atomic_store_explicit(&s->settings_busy,0u,memory_order_release);
    unlock(s);
    return result;
refuse:
    unlock(s);
    return refused;
}

FxResult fx_z63_h265_resource(void *context,uint32_t op,const FxNamedBinding *binding,
    FxPlatformOwner *owner,uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)binding;
    if(!owner || !cookie || !token)return FX_ARGUMENT;
    FxZ63VideoQuality *s=fx_z63_menu_video();
    if(!s || !atomic_load(&s->ready))return FX_STATE;
    if(op!=FX_RESOURCE_ATTACH && *cookie!=token)return FX_STALE;
    if(op==FX_RESOURCE_CALL && q && a && !q->arg[3] &&
       q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection)) {
        FxVideoQualitySelection choice;memcpy(&choice,q->data,sizeof(choice));
        if(choice.abi!=1u || choice.bytes!=sizeof(choice) || choice.family!=FX_VIDEO_FAMILY_H265)
            return FX_ARGUMENT;
        return fx_z63_h265_select(owner,token,choice.choice,0);
    }
    if(!lock(s))return FX_BUSY;
    FxVideoQualityPolicy *p=&s->h265;
    uint32_t idle=native_idle();
    FxResult result=FX_ARGUMENT;
    if(op==FX_RESOURCE_ATTACH) {
        if (atomic_load(&s->settings_busy)) result=FX_BUSY;
        else {
            uint32_t tier;
            if (!p->owner && fx_h265_settings_read(atomic_load(settings_word()),&tier))
                (void)fx_video_quality_select(p,token,tier,idle);
            if(p->owner==token)s->h265_owner=owner;
            *cookie=token;result=FX_OK;
        }
    } else if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC) {
        fx_z63_video_menu_unbind(owner,token);
        result=atomic_load(&s->settings_busy)?FX_BUSY:fx_video_quality_release(p,token,idle);
        if(result==FX_OK && op==FX_RESOURCE_DETACH)*cookie=0u;
    } else if(op==FX_RESOURCE_CALL && q && a && !q->arg[3]) {
        fx_video_quality_commit(p,idle);
        if(q->arg[2]==FX_VIDEO_QUALITY_QUERY && !q->bytes) {
            FxVideoQualityInfo info={1u,sizeof(info),FX_VIDEO_FAMILY_H265,31u,
                FX_VIDEO_QUALITY_PERSISTENT|FX_VIDEO_QUALITY_EXPERIMENTAL|FX_VIDEO_QUALITY_NATIVE_MENU,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS && !q->bytes) {
            uint32_t effective=atomic_load(&p->effective),fault=atomic_load(&p->fault);
            FxVideoQualityStatus info={1u,sizeof(info),FX_VIDEO_FAMILY_H265,p->requested,effective,
                p->registered==3u && idle && !p->active[0] && !p->active[1] && !fault && !atomic_load(&s->settings_busy),
                p->active[0],p->active[1],p->requested!=effective || p->retiring || atomic_load(&s->settings_busy),fault,p->transitions,0u};
            memcpy(a->data,&info,sizeof(info));a->bytes=sizeof(info);result=FX_OK;
        } else if(q->arg[2]==FX_VIDEO_QUALITY_MENU && q->bytes==sizeof(FxVideoQualityMenu)) {
            FxVideoQualityMenu request;memcpy(&request,q->data,sizeof(request));
            if(request.abi==1u && request.bytes==sizeof(request) && !request.reserved)
                result=fx_z63_video_menu_bind(owner,token,request.control,FX_VIDEO_FAMILY_H265);
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

extern uint32_t fx_z63_video_h265_metadata_original(const void *,void *);
uint32_t fx_z63_h265_metadata(const void *request,void *out) {
    uint32_t result=fx_z63_video_h265_metadata_original(request,out);
    if(result!=1u || !request || !out || ((const uint8_t *)request)[0xec])return result;
    uint32_t type,quality;
    memcpy(&type,(const uint8_t *)request+0x20u,4u);
    memcpy(&quality,(const uint8_t *)out+0xa8u,4u);
    if((type==2u || type==3u) && quality==1u) {
        FxZ63VideoQuality *s=fx_z63_menu_video();
        uint32_t tier=s?atomic_load_explicit(&s->h265.effective,memory_order_acquire):0u;
        if(tier>0u && tier<=4u) {
            quality=2u;memcpy((uint8_t *)out+0xa8u,&quality,4u);
        }
    }
    return result;
}
