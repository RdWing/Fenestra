/* Discovery and workers retain their published state through guest reboot.
 * No compile-time package name, size or allowlist controls this runtime. */
#include "runtime.h"
#include "discovery.h"
#include "fenestra_platform_native.h"
#include "fenestra_memory.h"
#include "fenestra_resident.h"
#include "fenestra_resources.h"
#ifdef FX_Z63_UI
#include "ui.h"
#include "fenestra_native_panic.h"
#endif
#define CAPS FX_SDK_CAPS
struct FxZ63Runtime {
    FxZ63TaskScope task;FxZ63Directory directory;FxModuleInventory inventory;
    FxZ63ModuleWorker **workers;FxZ63Services **services;
    FxResident **residents;FxPlatformOwner **owners;
    _Atomic uint32_t count,stop,published,error,exited;
#ifdef FX_Z63_UI
    FxNativePanicPage *panic;
#endif
    uint8_t scratch[16385];
};
const uint32_t fx_z63_runtime_layout[]={0x46585236u,1u,offsetof(FxZ63Runtime,services),
    offsetof(FxZ63Runtime,workers),offsetof(FxZ63Runtime,count)};
#ifdef FX_Z63_UI
const uint32_t fx_z63_panic_layout[]={0x46585036u,1u,offsetof(FxZ63Runtime,panic),
    offsetof(FxNativePanicPage,captured),offsetof(FxNativePanicPage,shown),offsetof(FxNativePanicPage,result),
    offsetof(FxNativePanicPage,display)+offsetof(FxNativeDisplay,frames),
    offsetof(FxNativePanicPage,report)+offsetof(FxPanicReport,cpu_faults),
    offsetof(FxNativePanicPage,report)+offsetof(FxPanicReport,esr)};
#endif
__attribute__((noinline)) void fx_z63_probe_module_result(uint32_t stage,uint32_t result,uint64_t detail) {
    __asm__ volatile(""::"r"(stage),"r"(result),"r"(detail):"memory");
}
void fx_native_module_fault(FxPlatformOwner *o,FxResult error) {
    if(!o)return;
    if(error==FX_OK)error=FX_INTEGRITY;
    uint32_t zero=0u;
    (void)atomic_compare_exchange_strong(&o->first_error,&zero,(uint32_t)error);
    atomic_store_explicit(&o->phase,FX_OWNER_FAULT,memory_order_release);
}
static void *allocate(void *context,uint32_t n){(void)context;return ((void *(*)(uint32_t,uint32_t))(uintptr_t)0x40d32d00u)(n,0u);}
static void release(void *context,void *p){(void)context;((void (*)(void *))(uintptr_t)0x40d32d40u)(p);}
static uint64_t clock_ms(void) {
    uint64_t n,hz;__asm__ volatile("mrs %0,cntpct_el0; mrs %1,cntfrq_el0":"=r"(n),"=r"(hz));
    return hz && hz<=UINT32_MAX?n/hz*1000u+n%hz*1000u/hz:UINT64_MAX;
}
static FxResult resident_owner_ready(void *context,FxPlatformOwner *owner) {
    (void)context;
#ifdef FX_Z63_UI
    return fx_z63_ui_register(owner);
#else
    (void)owner;return FX_OK;
#endif
}
static void request_stop(FxZ63Runtime *s,uint32_t panic) {
    for(uint32_t i=0u;i<atomic_load_explicit(&s->count,memory_order_acquire);++i) {
        if(s->residents[i])fx_resident_request_stop(s->residents[i],panic);
        else fx_z63_worker_shutdown(s->workers[i]);
    }
}
static void run_work(void *context) {
    FxZ63Runtime *s=context;FxModuleDirectory io;
    if(atomic_load(&s->stop)) {
        atomic_store_explicit(&s->published,1u,memory_order_release);return;
    }
    const FxPlatform *platform=fx_platform_target();
    FxResult r=fx_z63_directory_init(&s->directory,&io);
    if(r==FX_OK)r=fx_modules_discover(&io,platform->module_identity,CAPS,s->scratch,sizeof(s->scratch),&s->inventory,(FxIndexMemory){0,allocate,release});
    fx_z63_probe_module_result(60u,(uint32_t)r,s->inventory.count);
    if(r!=FX_OK || atomic_load(&s->stop)){atomic_store(&s->error,r?r:FX_STATE);return;}
    uint32_t count=s->inventory.count;
    if(count>65534u){atomic_store(&s->error,FX_BUDGET);fx_z63_probe_module_result(40u,FX_BUDGET,0u);return;}
    if(!count){atomic_store_explicit(&s->published,1u,memory_order_release);return;}
#ifdef FX_Z63_UI
    s->panic=allocate(0,(uint32_t)sizeof(*s->panic));
    if(!s->panic){atomic_store(&s->error,FX_BUDGET);return;}
    fx_native_panic_page_init(s->panic);
#endif
    s->workers=allocate(0,count*(uint32_t)sizeof(*s->workers));
    s->services=allocate(0,count*(uint32_t)sizeof(*s->services));
    s->residents=allocate(0,count*(uint32_t)sizeof(*s->residents));
    s->owners=allocate(0,count*(uint32_t)sizeof(*s->owners));
    if(!s->workers || !s->services || !s->residents || !s->owners){atomic_store(&s->error,FX_BUDGET);fx_z63_probe_module_result(40u,FX_BUDGET,0u);return;}
    memset(s->workers,0,count*sizeof(*s->workers));memset(s->services,0,count*sizeof(*s->services));
    memset(s->residents,0,count*sizeof(*s->residents));memset(s->owners,0,count*sizeof(*s->owners));
    for(uint32_t i=0;i<count && !atomic_load(&s->stop);++i) {
        const FxDiscoveredModule *entry=&s->inventory.entries[i];FxExecLayout layout;
        uint32_t caps=(entry->required|entry->optional)&CAPS;
        if(entry->entry_abi==FX_MODULE_ENTRY_NATIVE) {
            FxResidentHost host=fx_native_resident_host(platform);host.context=s;host.prepare_owner=resident_owner_ready;
            r=fx_resident_start(&s->residents[i],platform,entry,i+1u,1u,&io,host);
            s->owners[i]=fx_resident_owner(s->residents[i]);
            fx_z63_probe_module_result(90u,(uint32_t)r,i);
            fx_z63_probe_module_result(61u,(uint32_t)r,i);
            if(r!=FX_OK)atomic_store(&s->error,r);
            atomic_store_explicit(&s->count,i+1u,memory_order_release);
            if(atomic_load(&s->stop))fx_resident_request_stop(s->residents[i],0u);
            continue;
        }
        r=fx_z63_session_layout_stacks(entry->bytes,entry->image_bytes,entry->stacks,&layout);
        FxZ63Services *services=allocate(0,(uint32_t)sizeof(*services));
        void *worker=allocate(0,fx_z63_worker_bytes());
        void *session=r==FX_OK?allocate(0,layout.bytes+4096u):0;
        if(r==FX_OK && (!services || !worker || !session))r=FX_BUDGET;
        if(r==FX_OK) {
            memset(services,0,sizeof(*services));memset(worker,0,fx_z63_worker_bytes());
            r=fx_z63_services_init(services,i+1u,1u,caps);
#ifdef FX_Z63_UI
            if(r==FX_OK)r=fx_z63_ui_register(&services->platform);
#endif
        }
        if(r==FX_OK) {
            s->services[i]=services;
            s->owners[i]=&services->platform;
            r=fx_z63_worker_start(worker,fx_z63_worker_bytes(),session,layout.bytes+4096u,entry,i+1u,1u,caps,
                (FxServiceBackend){services,fx_z63_service_call,fx_z63_service_stop},&s->workers[i]);
        }
        fx_z63_probe_module_result(61u,(uint32_t)r,i);
        if(r!=FX_OK)atomic_store(&s->error,r);
        atomic_store_explicit(&s->count,i+1u,memory_order_release);
        if(atomic_load(&s->stop))fx_z63_worker_shutdown(s->workers[i]);
    }
    atomic_store_explicit(&s->published,1u,memory_order_release);
#ifdef FX_Z63_UI
    /* Inventory/worker publication is complete. Long-lived modules must not
     * freeze manager inspection or outlive the controller's observation. */
    fx_z63_ui_ready();
#endif
    uint32_t reported=0u;
    for(;;) {
        uint32_t finished=0,faulted=0,quiesced=0,n=atomic_load(&s->count);
        for(uint32_t i=0;i<n;++i) {
            if(s->residents[i]) {
                if(s->owners[i])fx_platform_pulse(s->owners[i],clock_ms());
                if(atomic_load(&s->stop))fx_resident_request_stop(s->residents[i],0u);
                uint32_t before=fx_resident_phase(s->residents[i]);
                FxResult result=fx_resident_poll(s->residents[i]);
                uint32_t phase=fx_resident_phase(s->residents[i]);
                if(before!=phase)fx_z63_probe_module_result(91u,phase,i);
                quiesced+=(uint32_t)(phase==FX_RESIDENT_STOPPED);
                faulted+=(uint32_t)(phase==FX_RESIDENT_FAULT || (result!=FX_OK && result!=FX_BUSY));
            } else {
                uint32_t phase=fx_z63_worker_phase(s->workers[i]);
                finished+=(uint32_t)(phase==FX_Z63_WORKER_FINISHED);
                quiesced+=(uint32_t)(phase==FX_Z63_WORKER_QUIESCED);
                faulted+=(uint32_t)(!s->workers[i] || phase==FX_Z63_WORKER_PANIC);
            }
        }
        if(faulted) {
            if(!reported) {
                /* The retained error page describes a stopped activation.
                 * Keep its controller alive to render, but retire every peer
                 * owner through the normal stop/ACK path before another tick. */
                request_stop(s,1u);
                fx_z63_probe_module_result(63u,faulted,finished);reported=1u;
            }
#ifdef FX_Z63_UI
            if(!s->panic->captured)for(uint32_t i=0u;i<n;++i) {
                if(s->residents[i] && fx_resident_error(s->residents[i])!=FX_OK) {
                    s->panic->report=(FxPanicReport){.module=fx_resident_identity(s->residents[i]),.error=fx_resident_error(s->residents[i])};
                    s->panic->captured=1u;break;
                }
                if(s->workers[i] && fx_z63_worker_panic_report(s->workers[i],&s->panic->report)==FX_OK){s->panic->captured=1u;break;}
            }
            if(s->panic->captured)(void)fx_native_panic_poll(s->panic);
#endif
        } else if(finished==n){fx_z63_probe_module_result(63u,0u,finished);break;}
        if(atomic_load(&s->stop) && quiesced==n)break;
        if(fx_z63_task_delay_ticks(10u)!=FX_OK){fx_z63_probe_module_result(40u,FX_IO,0u);return;}
    }
}
static void run(void *context){FxZ63Runtime *s=context;run_work(s);
#ifdef FX_Z63_UI
    if(s->panic && atomic_load(&s->stop)) {
        atomic_store_explicit(&s->panic->render_gate,0u,memory_order_release);
        fx_native_display_detach(&s->panic->display);
    }
    fx_z63_ui_ready();
#endif
    atomic_store_explicit(&s->exited,1u,memory_order_release);
}
void fx_z63_probe_module_start(void) {
    FxZ63Runtime *s=allocate(0,(uint32_t)sizeof(*s));void *stack=allocate(0,65536u+16u);
    if(!s || !stack){fx_z63_probe_module_result(2u,FX_BUDGET,0u);return;}
    memset(s,0,sizeof(*s));stack=(void *)(((uintptr_t)stack+15u)&~(uintptr_t)15u);
    fx_z63_menu_set_runtime(s);
    FxResult r=fx_z63_task_start(&s->task,run,s,stack,65536u);
    if(r!=FX_OK)atomic_store(&s->error,r);
    fx_z63_probe_module_result(4u,(uint32_t)r,(uint32_t)s->task.id);
}
void fx_z63_runtime_stop(FxZ63Runtime *s){if(!s)return;atomic_store(&s->stop,1u);request_stop(s,0u);}
uint32_t fx_z63_runtime_state(const FxZ63Runtime *s) {
    if(!s)return 0u;
    if(atomic_load(&s->error))return 2u;
    if(!atomic_load_explicit(&s->published,memory_order_acquire))return 0u;
    uint32_t count=atomic_load(&s->count),quiesced=0u,pending=0u;
    for(uint32_t i=0u;i<count;++i) {
        if(s->residents[i]) {
            uint32_t phase=fx_resident_phase(s->residents[i]);
            if(fx_resident_error(s->residents[i])!=FX_OK || phase==FX_RESIDENT_FAULT)return 2u;
            quiesced+=(uint32_t)(phase==FX_RESIDENT_STOPPED);
            pending+=(uint32_t)(phase==FX_RESIDENT_LOADING || phase==FX_RESIDENT_STOPPING || phase==FX_RESIDENT_EMPTY);
            continue;
        }
        uint32_t phase=fx_z63_worker_phase(s->workers[i]);
        if(phase==FX_Z63_WORKER_PANIC || !s->workers[i])return 2u;
        quiesced+=(uint32_t)(phase==FX_Z63_WORKER_QUIESCED);
        pending+=(uint32_t)(phase==FX_Z63_WORKER_LOADING || phase==FX_Z63_WORKER_EMPTY || phase==FX_Z63_WORKER_STOPPING);
    }
    if(atomic_load(&s->stop) && quiesced==count)
        return atomic_load_explicit(&s->exited,memory_order_acquire)?3u:0u;
    return pending?0u:1u;
}
uint32_t fx_z63_runtime_count(const FxZ63Runtime *s){return s?atomic_load_explicit(&s->count,memory_order_acquire):0u;}
FxZ63ModuleWorker *fx_z63_runtime_worker(const FxZ63Runtime *s,uint32_t i){return s && i<fx_z63_runtime_count(s)?s->workers[i]:0;}
FxPlatformOwner *fx_z63_runtime_owner(const FxZ63Runtime *s,uint32_t i){return s && i<fx_z63_runtime_count(s)?s->owners[i]:0;}
const char *fx_z63_runtime_identity(const FxZ63Runtime *s,uint32_t i){
    if(!s || i>=fx_z63_runtime_count(s))return 0;
    return s->residents[i]?fx_resident_identity(s->residents[i]):fx_z63_worker_identity(s->workers[i]);
}
