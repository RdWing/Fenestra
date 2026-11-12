#include <assert.h>
#include <string.h>
#include "fenestra_platform.h"
#include "fenestra_extensions.h"
#ifdef FX_LOG_APP
#include "../modules/log3g10/module.c"
#define TEST_FAMILY FX_VIDEO_FAMILY_COLOR
#define TEST_PROVIDER FX_VIDEO_COLOR_PROVIDER
#define TEST_ACTIVE "Log3G10 / RWG"
#define TEST_REFUSED "Selection refused"
#define TEST_RETAINED "Log3G10 retained. Restart"
#else
#include "../modules/r3dne/module.c"
#define TEST_FAMILY FX_VIDEO_FAMILY_RAW
#define TEST_PROVIDER FX_VIDEO_RAW_PROVIDER
#define TEST_ACTIVE "R3D NE"
#define TEST_REFUSED "Select N-RAW first"
#define TEST_RETAINED "R3D NE retained. Restart"
#endif
FxExtensionDomain *fx_native_extensions(FxPlatformOwner *p){(void)p;return 0;}
static uint32_t conflict,busy_replies,status_calls;
static FxVideoQualityPolicy policy;
static FxPlatformOwner owner;
static FxServiceOwner service_owner;
static FxServiceExchange exchange;
#define RAW_MODULE_CAPABILITIES UINT32_C(0x390000)
_Static_assert(RAW_MODULE_CAPABILITIES==(FX_SDK_QUERY|FX_SDK_NATIVE|FX_SDK_MENU|FX_SDK_BINDING),
    "The fixture must use the R3D module package capabilities");
static uint32_t module_capabilities=RAW_MODULE_CAPABILITIES;
static uint32_t open_calls,resource_calls,attach_calls;
static FxResult open_result=FX_STATE;
static uint32_t idle=1u,commits,busy_once,menu_attached,no_menu,bad_mode,stock_only;
static FxResult resource(void *context,uint32_t op,const FxNamedBinding *descriptor,FxPlatformOwner *caller,
    uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;(void)descriptor;(void)caller;++resource_calls;
    if(op==FX_RESOURCE_ATTACH){++attach_calls;*cookie=token;return FX_OK;}
    assert(*cookie==token);
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC){menu_attached=0u;return fx_video_quality_release(&policy,token,idle);}
    assert(op==FX_RESOURCE_CALL && q && a);
    if(q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
        FxVideoQualityInfo info={1u,sizeof(info),TEST_FAMILY,stock_only?1u:3u,(stock_only?FX_VIDEO_QUALITY_UNAVAILABLE:0u)|(no_menu?0u:FX_VIDEO_QUALITY_NATIVE_MENU)|3u,0u};a->bytes=sizeof(info);memcpy(a->data,&info,sizeof(info));
    } else if(q->arg[2]==FX_VIDEO_QUALITY_MENU) {
        assert(!no_menu);assert(q->bytes==sizeof(FxVideoQualityMenu));FxVideoQualityMenu request;memcpy(&request,q->data,sizeof(request));
        assert(request.abi==1u && request.bytes==sizeof(request) && request.control==2u && !request.reserved);++menu_attached;
    } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
        ++status_calls;fx_video_quality_commit(&policy,idle);
        FxVideoQualityStatus snapshot={1u,sizeof(snapshot),TEST_FAMILY,policy.requested,atomic_load(&policy.effective),idle,
            policy.active[0],policy.active[1],policy.requested!=atomic_load(&policy.effective),atomic_load(&policy.fault),commits,0u};
        a->bytes=sizeof(snapshot);memcpy(a->data,&snapshot,sizeof(snapshot));
    } else {
        assert(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection));
        FxVideoQualitySelection selection;memcpy(&selection,q->data,sizeof(selection));
        assert(selection.family==TEST_FAMILY);
        if(bad_mode && selection.choice)return FX_STATE;
        if(conflict && selection.choice){++busy_replies;return FX_BUSY;}
        if(busy_once){busy_once=0u;return FX_BUSY;}
        FxResult r=fx_video_quality_select(&policy,token,selection.choice,idle);if(r==FX_OK)++commits;return r;
    }
    return FX_OK;
}
static FxResult service(void *context,const FxServiceRequest *q,FxServiceReply *a){
    FxResult result=fx_platform_dispatch(context,q,a);
    if(q->operation==FX_S_PLATFORM && q->arg[0]==FX_BIND_OPEN){++open_calls;open_result=result;}
    return result;
}
static FxResult stop(void *context,uint32_t panic){return fx_platform_stop(context,panic);}
static FxUiControl row(uint32_t id) {
    FxUiControl controls[16];uint32_t count=0u,revision=0u;
    assert(fx_ui_snapshot(&owner,controls,16u,&count,&revision)==FX_OK);
    for(uint32_t i=0u;i<count;++i)if(controls[i].id==id)return controls[i];
    assert(0);return controls[0];
}
static void steps(uint32_t count) {
    FxServiceModule api={.base={.bytes=sizeof(FxServiceModule)},.service_abi=FX_SERVICE_ABI,
        .owner=1u,.generation=1u,.capabilities=module_capabilities,.exchange=&exchange};
    assert(api.capabilities==service_owner.capabilities && api.capabilities==owner.capabilities);
    for(uint32_t i=0u;i<count;++i) {
        assert(fenestra_module_entry(&api.base)==0);
        (void)fx_service_dispatch(&service_owner,&exchange.request,&exchange.reply);
    }
}
#include "video_module_retry_cases.h"
int main(int argc,char **argv) {
    FxNamedBinding descriptor={.name=TEST_PROVIDER,.kind=FX_BIND_DEVICE,.abi=FX_CALL_DEVICE,
        .version=1u,.flags=FX_BIND_PROVIDER,.capabilities=FX_SDK_NATIVE,.address=1u};
    if(argc==2 && !strcmp(argv[1],"old-core"))descriptor.name="unavailable";
    uint32_t missing_native=(argc==2 && !strcmp(argv[1],"missing-native"))?1u:0u;
    if(missing_native){module_capabilities&=~FX_SDK_NATIVE;assert(module_capabilities==UINT32_C(0x310000));}
    no_menu=1u;stock_only=argc==2 && !strcmp(argv[1],"stock-only");
    FxPlatform platform={.abi=1u,.count=1u,.bindings=&descriptor,.io={.resource=resource}};
    assert(fx_platform_init(&owner,&platform,1u,1u,module_capabilities)==FX_OK);
    fx_service_init(&service_owner,1u,1u,module_capabilities,(FxServiceBackend){&owner,service,stop});
    fx_video_quality_init(&policy);policy.registered=3u;steps(160u);
    assert(open_calls==1u);
    if(missing_native || (argc==2 && !strcmp(argv[1],"old-core"))){
        assert(open_result==FX_CAPABILITY && !resource_calls && !attach_calls);
        assert(!owner.binding_count && !binding && !policy.owner && !policy.requested);
        assert(!atomic_load(&policy.effective) && !policy.transitions && !commits);
        assert(!(row(2u).flags&FX_UI_ENABLED) && !strcmp(row(3u).text,"Unavailable"));
        assert(!strcmp(row(4u).label,"Target path unqualified"));
        if(missing_native)assert(!strcmp(descriptor.name,TEST_PROVIDER));
        steps(160u);assert(open_calls==1u && !resource_calls && !owner.binding_count);
        assert(fx_platform_stop(&owner,0u)==FX_OK && !resource_calls);
        return 0;
    }
    assert(open_result==FX_OK && attach_calls==1u && owner.binding_count==1u && binding);
    if(stock_only) {
        assert(!(row(2u).flags&FX_UI_ENABLED) && !strcmp(row(3u).text,"Unavailable"));
        assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,1u)==FX_EMPTY);
        steps(160u);assert(!commits && !policy.owner);
        assert(fx_platform_stop(&owner,0u)==FX_OK);return 0;
    }
    assert(!menu_attached && row(2u).option_count==2u && (row(2u).flags&FX_UI_ENABLED));
    assert(!strcmp(row(3u).text,"Stock"));
    if(argc==2 && !strncmp(argv[1],"retry-",6u)){retry_case(argv[1],1u,0u);return 0;}
    bad_mode=1u;assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,1u)==FX_OK);steps(160u);
    assert(!commits && row(2u).value==0u && !strcmp(row(3u).text,TEST_REFUSED));
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,0u)==FX_OK);steps(160u);
    assert(!atomic_load(&policy.effective) && !strcmp(row(3u).text,"Stock"));commits=0u;
    bad_mode=0u;
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,1u)==FX_OK);busy_once=1u;steps(160u);
    assert(atomic_load(&policy.effective)==1u && commits==1u && !strcmp(row(3u).text,TEST_ACTIVE));
    assert(fx_video_quality_select(&policy,UINT64_C(0x1234),0u,idle)==FX_BUSY);
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,0u)==FX_OK);idle=0u;steps(160u);
    assert(atomic_load(&policy.effective)==1u && !strcmp(row(3u).text,"Waiting for idle"));
    idle=1u;steps(160u);assert(!atomic_load(&policy.effective) && !strcmp(row(3u).text,"Stock"));
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,1u)==FX_OK);steps(160u);
    if(argc==2 && !strcmp(argv[1],"active-fault")) {
        uint64_t retained_owner=policy.owner;uint32_t retained_transitions=policy.transitions;
        atomic_store(&policy.fault,1u);steps(160u);
        assert(row(2u).value==1u && !strcmp(row(3u).text,TEST_RETAINED));
        assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,0u)==FX_OK);steps(160u);
        assert(policy.requested==1u && atomic_load(&policy.effective)==1u && policy.owner==retained_owner);
        assert(policy.transitions==retained_transitions && row(2u).value==1u);
        assert(!strcmp(row(3u).text,TEST_RETAINED));
        assert(fx_platform_stop(&owner,0u)==FX_BUSY && policy.retiring && policy.requested==0u);
        assert(atomic_load(&policy.effective)==1u && policy.owner==retained_owner);
        assert(fx_platform_stop(&owner,1u)==FX_BUSY && atomic_load(&policy.effective)==1u);
        return 0;
    }
    idle=0u;assert(fx_platform_stop(&owner,0u)==FX_BUSY && atomic_load(&policy.effective)==1u);
    idle=1u;assert(fx_platform_stop(&owner,0u)==FX_OK && !atomic_load(&policy.effective));
    return 0;
}
