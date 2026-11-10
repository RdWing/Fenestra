#include <assert.h>
#include <string.h>
#include "fenestra_platform.h"
#include "fenestra_extensions.h"
#ifdef FX_H265_APP
#include "../modules/h265/module.c"
#else
#include "../modules/prores/module.c"
#endif
FxExtensionDomain *fx_native_extensions(FxPlatformOwner *p){(void)p;return 0;}
static uint32_t conflict,busy_replies,status_calls;
static FxVideoQualityPolicy policy;
static FxPlatformOwner owner;
static FxServiceOwner service_owner;
static FxServiceExchange exchange;
static uint32_t idle=1u,commits,busy_once,menu_attached,no_menu,wrong_mode;
static FxResult resource(void *context,uint32_t op,const FxNamedBinding *descriptor,FxPlatformOwner *caller,
    uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)descriptor;(void)caller;
    if(op==FX_RESOURCE_ATTACH){*cookie=token;return FX_OK;}
    assert(*cookie==token);
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC){menu_attached=0u;return fx_video_quality_release(&policy,token,idle);}
    assert(op==FX_RESOURCE_CALL && q && a);
    if(q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
        FxVideoQualityInfo info={1u,sizeof(info),FX_CHOICE_FAMILY,31u,(no_menu?0u:FX_VIDEO_QUALITY_NATIVE_MENU)|3u,0u};a->bytes=sizeof(info);memcpy(a->data,&info,sizeof(info));
    } else if(q->arg[2]==FX_VIDEO_QUALITY_MENU) {
        assert(!no_menu);assert(q->bytes==sizeof(FxVideoQualityMenu));FxVideoQualityMenu request;memcpy(&request,q->data,sizeof(request));
        assert(request.abi==1u && request.bytes==sizeof(request) && request.control==2u && !request.reserved);++menu_attached;
    } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
        ++status_calls;fx_video_quality_commit(&policy,idle);
        FxVideoQualityStatus snapshot={1u,sizeof(snapshot),FX_CHOICE_FAMILY,policy.requested,atomic_load(&policy.effective),idle,
            policy.active[0],policy.active[1],policy.requested!=atomic_load(&policy.effective),atomic_load(&policy.fault),commits,0u};
        a->bytes=sizeof(snapshot);memcpy(a->data,&snapshot,sizeof(snapshot));
    } else {
        assert(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection));
        FxVideoQualitySelection selection;memcpy(&selection,q->data,sizeof(selection));
        assert(selection.family==FX_CHOICE_FAMILY);
        if(wrong_mode && selection.choice)return FX_STATE;
        if(conflict && selection.choice){++busy_replies;return FX_BUSY;}
        if(busy_once){busy_once=0u;return FX_BUSY;}
        FxResult r=fx_video_quality_select(&policy,token,selection.choice,idle);if(r==FX_OK)++commits;return r;
    }
    return FX_OK;
}
static FxResult service(void *context,const FxServiceRequest *q,FxServiceReply *a){return fx_platform_dispatch(context,q,a);}
static FxResult stop(void *context,uint32_t panic){return fx_platform_stop(context,panic);}
static FxUiControl row(uint32_t id) {
    FxUiControl controls[16];uint32_t count=0u,revision=0u;
    assert(fx_ui_snapshot(&owner,controls,16u,&count,&revision)==FX_OK);
    for(uint32_t i=0u;i<count;++i)if(controls[i].id==id)return controls[i];
    assert(0);return controls[0];
}
static void steps(uint32_t count) {
    FxServiceModule api={.base={.bytes=sizeof(FxServiceModule)},.service_abi=FX_SERVICE_ABI,
        .owner=1u,.generation=1u,.capabilities=FX_SDK_CAPS,.exchange=&exchange};
    for(uint32_t i=0u;i<count;++i) {
        assert(fenestra_module_entry(&api.base)==0);
        (void)fx_service_dispatch(&service_owner,&exchange.request,&exchange.reply);
    }
}
#include "video_module_retry_cases.h"
int main(int argc,char **argv) {
    (void)argv;FxNamedBinding descriptor={.name=FX_CHOICE_PROVIDER,.kind=FX_BIND_DEVICE,.abi=FX_CALL_DEVICE,
        .version=1u,.flags=FX_BIND_PROVIDER,.capabilities=FX_SDK_NATIVE,.address=1u};
    if(argc==2 && !strcmp(argv[1],"old-core"))descriptor.name="unavailable";
    no_menu=argc==2 && !strcmp(argv[1],"no-menu");
#ifdef FX_H265_APP
    no_menu=1u;
#endif
    FxPlatform platform={.abi=1u,.count=1u,.bindings=&descriptor,.io={.resource=resource}};
    assert(fx_platform_init(&owner,&platform,1u,1u,FX_SDK_CAPS)==FX_OK);
    fx_service_init(&service_owner,1u,1u,FX_SDK_CAPS,(FxServiceBackend){&owner,service,stop});
    fx_video_quality_init(&policy);policy.registered=3u;steps(160u);
    if(argc==2 && !strcmp(argv[1],"old-core")){assert(!(row(2u).flags&FX_UI_ENABLED) && !strcmp(row(4u).label,"Requires updated core"));return 0;}
    assert(menu_attached==(no_menu?0u:1u) && row(2u).option_count==5u && (row(2u).flags&FX_UI_ENABLED));
    assert(!strcmp(row(3u).text,names[0]));
#ifdef FX_H265_APP
    wrong_mode=1u;
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,FX_VIDEO_HQ)==FX_OK);steps(160u);
    assert(!atomic_load(&policy.effective) && row(2u).value==0u);
    assert(!strcmp(row(3u).text,FX_CHOICE_MODE_NOTE));
    wrong_mode=0u;
#endif
    if(argc==2 && !strncmp(argv[1],"retry-",6u)){retry_case(argv[1],FX_VIDEO_LT,FX_VIDEO_PROXY);return 0;}
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,FX_VIDEO_LT)==FX_OK);busy_once=1u;steps(160u);
    assert(atomic_load(&policy.effective)==FX_VIDEO_LT && commits==1u && !strcmp(row(3u).text,names[FX_VIDEO_LT]));
    assert(fx_video_quality_select(&policy,UINT64_C(0x1234),FX_VIDEO_HQ,idle)==FX_BUSY);
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,FX_VIDEO_PROXY)==FX_OK);idle=0u;steps(160u);
    assert(atomic_load(&policy.effective)==FX_VIDEO_LT && !strcmp(row(3u).text,"Waiting for idle"));
    idle=1u;steps(160u);assert(atomic_load(&policy.effective)==FX_VIDEO_PROXY && !strcmp(row(3u).text,names[FX_VIDEO_PROXY]));
    assert(fx_video_quality_select(&policy,policy.owner,FX_VIDEO_STANDARD,idle)==FX_OK);steps(160u);
    assert(row(2u).value==FX_VIDEO_STANDARD && !strcmp(row(3u).text,names[FX_VIDEO_STANDARD]));
    idle=0u;assert(fx_platform_stop(&owner,0u)==FX_BUSY && atomic_load(&policy.effective)==FX_VIDEO_STANDARD);
    idle=1u;assert(fx_platform_stop(&owner,0u)==FX_OK && !atomic_load(&policy.effective) && !menu_attached);
    return 0;
}
