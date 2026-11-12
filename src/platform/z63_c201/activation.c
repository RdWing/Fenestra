#include "activation.h"
#include "fenestra_memory.h"
#include "fenestra_mmu_context.h"
#include "z63_debug_identity.h"
#define CONTROL UINT64_C(0x40194fe0)
#define CONTROL_RAM UINT64_C(0xa1722cfe0)
#define FN(a,t) ((t)(uintptr_t)(a))
#include "z63_ram_hooks.h"
static _Atomic uint32_t *latch(void){return (_Atomic uint32_t *)(uintptr_t)CONTROL_RAM;}
static _Atomic uint32_t *resume_word(void){return latch()+1;}
static void persist_control(void) {
    /* A standby reset may discard caches while retaining DRAM/code. The
     * update veto and wake commitment must reach PoC before their dependents. */
    uintptr_t address=CONTROL_RAM;
    __asm__ volatile("dc cvac,%0; dsb sy"::"r"(address):"memory");
}
static uintptr_t alias(uint32_t va) {
    if(va>=0x40168000u && va<=0x40194ffcu)return UINT64_C(0xa17200000)+va-0x40168000u;
    if(va>=0x40200000u && va<=0x4090ebe4u)return UINT64_C(0xa15c00000)+va-0x40200000u;
    if(va>=0x40c00000u && va<=0x416692f4u)return UINT64_C(0xa16600000)+va-0x40c00000u;
    return 0u;
}
static FxResult mapping(void *context,const FxActivationWord *row) {
    (void)context;
    uintptr_t pa=alias(row->site);if(!pa || (row->site&3u))return FX_CAPABILITY;
    const FxNativeMmuContext *source=(const void *)(uintptr_t)UINT64_C(0xa04edb048);
    FxNativeMmuContext view=*source;
    uintptr_t roots[4]={view.root,view.roots[0],view.roots[1],view.roots[2]};
    uint32_t count=view.private_roots?4u:1u;
    view.private_roots=0u;
    /* Verify executable and writable aliases in every native root. This
     * never changes mappings, and refuses an unexpected flash mapping. */
    for(uint32_t i=0;i<count;++i) {
        if(!roots[i] || (roots[i]&4095u))return FX_INTEGRITY;
        view.root=roots[i];
        for(uint32_t j=0;j<2u;++j) {
            uint64_t physical=0u;uint32_t attributes=0u;uintptr_t va=j?pa:row->site;
            if(FN(0x401751dcu,int32_t (*)(void *,uint64_t,uint64_t *,int32_t))(&view,va,&physical,-1) ||
               FN(0x40175248u,int32_t (*)(void *,uint64_t,uint32_t *,int32_t))(&view,va,&attributes,-1) ||
               physical!=pa || (j?(attributes&1u):!(attributes&2u)))return FX_CAPABILITY;
        }
    }
    if(source->root!=roots[0] || (!!source->private_roots)!=(count==4u))return FX_BUSY;
    if(count==4u)for(uint32_t i=0;i<3u;++i)if(source->roots[i]!=roots[i+1u])return FX_BUSY;
    return FX_OK;
}
static uint32_t read_word(void *context,const FxActivationWord *row) {
    (void)context;return atomic_load_explicit((_Atomic uint32_t *)alias(row->site),memory_order_acquire);
}
static FxResult exchange(void *context,const FxActivationWord *row,uint32_t old,uint32_t next) {
    (void)context;
    return atomic_compare_exchange_strong_explicit((_Atomic uint32_t *)alias(row->site),&old,next,
        memory_order_acq_rel,memory_order_acquire)?FX_OK:FX_INTEGRITY;
}
static FxResult synchronize(void *context,const FxActivationWord *row) {
    (void)context;uintptr_t pa=alias(row->site);
    /* Data clean reaches PoC, including retained DRAM; invalidate instruction caches for the inner
     * shareable domain. Hardware fetch/coherency timing is a device gate. */
    __asm__ volatile("dc cvac,%0; dsb ish; ic ialluis; dsb ish; isb"::"r"(pa):"memory");
    return read_word(0,row)==*(const volatile uint32_t *)(uintptr_t)row->site?FX_OK:FX_INTEGRITY;
}
static const FxActivationMemory memory={0,mapping,read_word,exchange,synchronize};
int fx_z63_activation_updating(void) {
    return atomic_load_explicit(latch(),memory_order_acquire)==FX_ACT_UPDATE;
}
int fx_z63_activation_update_requires_restart(void) {
    uint32_t session=atomic_load_explicit(latch(),memory_order_acquire);
    return session!=FX_ACT_CLEAN && session!=FX_ACT_UPDATE;
}
uint32_t fx_z63_activation_shell_enter(void) {
    uint32_t clean=FX_ACT_CLEAN;
    if(atomic_compare_exchange_strong(latch(),&clean,FX_ACT_BOOTSTRAP)) {
        persist_control();return FX_ACT_BOOTSTRAP;
    }
    /* Retained modified text already excludes updates. A clean initializer
     * needs a temporary lease so an updater cannot race its allocations. */
    return clean==FX_ACT_MODIFIED?FX_ACT_MODIFIED:0u;
}
void fx_z63_activation_shell_leave(uint32_t lease) {
    if(lease!=FX_ACT_BOOTSTRAP)return;
    uint32_t expected=FX_ACT_BOOTSTRAP;
    (void)atomic_compare_exchange_strong(latch(),&expected,FX_ACT_CLEAN);
    persist_control();
}
void fx_z63_activation_init(FxZ63Activation *s) {
    memset(s,0,sizeof(*s));
    /* Retained code is not enough: require the original MAIN wake decision
     * and a committed prior activation. Cold/stale-data fixtures do not arm. */
    s->resume=atomic_load_explicit(latch(),memory_order_acquire)==FX_ACT_MODIFIED &&
        atomic_load_explicit(resume_word(),memory_order_acquire)==1u &&
        *(const volatile uint32_t *)(uintptr_t)UINT64_C(0xa035d9f00)==1u &&
        *(const volatile uint32_t *)(uintptr_t)UINT64_C(0xa035d9fb8)==1u;
}
static FxResult enable_file(FxStartupFiles *files) {
    if(atomic_load(&files->uncertain) || atomic_load(files->shutdown))return FX_STATE;
    const FxStartupFileProfile *p=files->profile;
    int32_t fd=p->open("A:\\FENESTRA\\FX63ARM.BIN",0u,0u);
    if((uint32_t)fd==p->missing)return FX_EMPTY;
    if(fd<0)return FX_IO;
    uint8_t data[65];uint32_t size=0;FxResult result=FX_OK;
    while(size<sizeof(data)) {
        uint32_t done=0u,room=(uint32_t)sizeof(data)-size;
        if(p->read(fd,data+size,room,&done)){result=FX_IO;break;}
        if(done>room){result=FX_INTEGRITY;break;}
        size+=done;if(!done)break;
    }
    if(p->close(fd)){atomic_store(&files->uncertain,1u);return FX_CLOSE;}
    if(result!=FX_OK)return result;
    return fx_activation_record(data,size,fx_z63_debug_build);
}
FxResult fx_z63_activation_admit(FxZ63Activation *s,FxStartupFiles *files) {
    uint32_t phase=atomic_load(&s->phase);
    if((phase!=FX_ACT_STOCK && phase!=FX_ACT_VALIDATING) || fx_z63_activation_updating())return FX_STATE;
    FxResult r=enable_file(files);
    FxActivationWord control={(uint32_t)CONTROL,0u,1u};
    if(r==FX_OK)r=mapping(0,&control);
    if(r==FX_OK && atomic_load(files->shutdown))r=FX_STATE;
    if(r==FX_OK)r=fx_activation_claim(latch(),s->resume || phase==FX_ACT_VALIDATING);
    atomic_store(&s->error,r);
    if(r==FX_OK) {
        atomic_store_explicit(resume_word(),0u,memory_order_release);
        persist_control();
        atomic_store_explicit(&s->phase,FX_ACT_VALIDATING,memory_order_release);
    }
    return r;
}
FxResult fx_z63_activation_install(FxZ63Activation *s) {
    if(atomic_load(&s->phase)!=FX_ACT_VALIDATING)return FX_STATE;
    FxResult r=fx_activation_install(fx_z63_activation_words,fx_z63_activation_count,&memory,s->resume,&s->owned);
    atomic_store(&s->error,r);
    if(r!=FX_OK) {
        atomic_store(&s->phase,FX_ACT_FAULT);atomic_store_explicit(resume_word(),3u,memory_order_release);
        persist_control();
    }
    return r;
}
FxResult fx_z63_activation_restore(FxZ63Activation *s) {
    FxResult r=fx_activation_restore(fx_z63_activation_words,fx_z63_activation_count,&memory,&s->owned);
    atomic_store(&s->error,r);atomic_store(&s->phase,r==FX_OK?FX_ACT_LATCHED:FX_ACT_FAULT);
    return r;
}
void fx_z63_activation_running(FxZ63Activation *s,uint64_t token) {
    *(volatile uint64_t *)(uintptr_t)(CONTROL_RAM+8u)=token;
    uint32_t preparing=FX_ACT_VALIDATING,uncommitted=0u;
    /* A late worker acknowledgement must never undo retirement's wake veto.
     * Both publications are conditional; retirement wins either ordering. */
    if(!atomic_compare_exchange_strong(&s->phase,&preparing,FX_ACT_ACTIVE))return;
    if(!atomic_compare_exchange_strong_explicit(resume_word(),&uncommitted,1u,memory_order_release,memory_order_relaxed)) {
        uint32_t active=FX_ACT_ACTIVE;
        (void)atomic_compare_exchange_strong(&s->phase,&active,FX_ACT_FAULT);
    }
    persist_control();
}
uint64_t fx_z63_activation_token(void) {
    return *(const volatile uint64_t *)(uintptr_t)(CONTROL_RAM+8u);
}
void fx_z63_activation_retire(FxZ63Activation *s,int resume) {
    s->wake_after_drain=(uint32_t)!!resume;
    atomic_store(&s->phase,FX_ACT_DRAINING);
    /* A completed shutdown may set this back to 1. Until then a reset or
     * uncertain drain refuses automatic wake activation. */
    atomic_store_explicit(resume_word(),resume?3u:2u,memory_order_release);
    persist_control();
}
void fx_z63_activation_cleaned(FxZ63Activation *s,FxResult result) {
    atomic_store(&s->error,result);
    atomic_store_explicit(resume_word(),result==FX_OK?(s->wake_after_drain?1u:2u):3u,memory_order_release);
    persist_control();
    if(result!=FX_OK)atomic_store(&s->phase,FX_ACT_FAULT);
}
