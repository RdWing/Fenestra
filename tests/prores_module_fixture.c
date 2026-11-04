#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_native_sdk.h"
#include "../modules/prores/module.c"

extern int fenestra_native_entry(const FxNativeBootstrap *,FxNativeExports *);
static FxExtensionDomain *domain;
static FxVideoQualityPolicy policy;
static FxPlatformOwner ui_owner,native_owner,other_owner;
static FxServiceOwner ui_service,native_service;
static FxServiceExchange exchange;
static uint32_t idle=1u,commits,busy_once;
static void *allocate(void *context,uint32_t bytes){(void)context;return calloc(1u,bytes);}
static void release(void *context,void *memory){(void)context;free(memory);}
FxExtensionDomain *fx_native_extensions(FxPlatformOwner *owner){(void)owner;return domain;}
static FxResult resource(void *context,uint32_t op,const FxNamedBinding *descriptor,FxPlatformOwner *owner,
    uint64_t token,uint64_t *cookie,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;
    if(!strcmp(descriptor->name,"core.providers"))return fx_extensions_resource(domain,op,descriptor,owner,token,cookie,q,a);
    assert(!strcmp(descriptor->name,FX_VIDEO_QUALITY_PROVIDER));
    if(op==FX_RESOURCE_ATTACH){*cookie=token;return FX_OK;}
    assert(*cookie==token);
    if(op==FX_RESOURCE_DETACH || op==FX_RESOURCE_PANIC)return fx_video_quality_release(&policy,token,idle);
    assert(op==FX_RESOURCE_CALL && q && a);
    if(q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
        FxVideoQualityInfo info={1u,sizeof(info),1u,31u,3u,0u};a->bytes=sizeof(info);memcpy(a->data,&info,sizeof(info));
    } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
        fx_video_quality_commit(&policy,idle);
        FxVideoQualityStatus snapshot={1u,sizeof(snapshot),1u,policy.requested,atomic_load(&policy.effective),idle,
            policy.active[0],policy.active[1],policy.requested!=atomic_load(&policy.effective),atomic_load(&policy.fault),commits,0u};
        a->bytes=sizeof(snapshot);memcpy(a->data,&snapshot,sizeof(snapshot));
    } else {
        assert(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection));
        FxVideoQualitySelection selection;memcpy(&selection,q->data,sizeof(selection));
        if(busy_once){busy_once=0u;return FX_BUSY;}
        FxResult r=fx_video_quality_select(&policy,token,selection.choice,idle);if(r==FX_OK)++commits;return r;
    }
    return FX_OK;
}
static FxResult service(void *context,const FxServiceRequest *q,FxServiceReply *a){return fx_platform_dispatch(context,q,a);}
static FxResult stop(void *context,uint32_t panic){return fx_platform_stop(context,panic);}
static FxResult direct(void *context,const FxServiceRequest *q,FxServiceReply *a) {
    (void)context;FxServiceRequest copied=*q;copied.generation=native_owner.generation;
    copied.sequence=(uint32_t)native_service.last_sequence+1u;
    FxResult r=fx_service_dispatch(&native_service,&copied,a);a->sequence=q->sequence;return r;
}
static FxResult publish(void *context,const FxProviderDeclaration *declaration,uint64_t *token) {
    (void)context;return fx_provider_publish(domain,&native_owner,declaration,token);
}
static FxResult unpublish(void *context,uint64_t token){(void)context;return fx_provider_remove(domain,&native_owner,token);}
static FxUiControl row(uint32_t id) {
    FxUiControl controls[16];uint32_t count=0u,revision=0u;
    assert(fx_ui_snapshot(&ui_owner,controls,16u,&count,&revision)==FX_OK);
    for(uint32_t i=0u;i<count;++i)if(controls[i].id==id)return controls[i];
    abort();
}
static void steps(uint32_t count) {
    FxServiceModule api={.base={.bytes=sizeof(FxServiceModule)},.service_abi=FX_SERVICE_ABI,
        .owner=1u,.generation=1u,.capabilities=FX_SDK_CAPS,.exchange=&exchange};
    for(uint32_t i=0u;i<count;++i) {
        assert(fenestra_module_entry(&api.base)==0);
        (void)fx_service_dispatch(&ui_service,&exchange.request,&exchange.reply);
    }
}
static FxResult select_other(uint64_t token,uint32_t value) {
    FxVideoQualitySelection selection={1u,sizeof(selection),1u,value};FxServiceReply response={0};
    return fx_provider_call(domain,&other_owner,token,FX_VIDEO_QUALITY_SELECT,&selection,sizeof(selection),&response);
}
int main(int argc,char **argv) {
    FxNamedBinding bindings[]={
        {.name="core.providers",.kind=FX_BIND_DEVICE,.abi=FX_CALL_DEVICE,.version=1u,.flags=FX_BIND_PROVIDER,.capabilities=FX_SDK_BINDING,.address=1u},
        {.name=FX_VIDEO_QUALITY_PROVIDER,.kind=FX_BIND_DEVICE,.abi=FX_CALL_DEVICE,.version=1u,.flags=FX_BIND_PROVIDER,.capabilities=FX_SDK_NATIVE,.address=1u}};
    FxPlatform platform={.abi=1u,.count=2u,.bindings=bindings,.io={.resource=resource}};
    int old_core=argc==2 && !strcmp(argv[1],"old-core");
    int no_video=argc==2 && !strcmp(argv[1],"no-video");
    if(old_core){platform.count=1u;platform.bindings=bindings+1u;}
    if(no_video)platform.count=1u;
    assert(fx_platform_init(&ui_owner,&platform,1u,1u,FX_SDK_CAPS)==FX_OK);
    assert(fx_platform_init(&native_owner,&platform,2u,1u,FX_SDK_CAPS)==FX_OK);
    assert(fx_platform_init(&other_owner,&platform,3u,1u,FX_SDK_CAPS)==FX_OK);
    fx_service_init(&ui_service,1u,1u,FX_SDK_CAPS,(FxServiceBackend){&ui_owner,service,stop});
    fx_service_init(&native_service,2u,1u,FX_SDK_CAPS,(FxServiceBackend){&native_owner,service,stop});
    domain=fx_extensions_create((FxIndexMemory){0,allocate,release},1024u*1024u);assert(domain);
    fx_video_quality_init(&policy);policy.registered=3u;
    steps(160u);
    assert(!(row(2u).flags&FX_UI_ENABLED));
    if(old_core){assert(!strcmp(row(4u).label,"Requires updated core"));return 0;}
    assert(!strcmp(row(4u).label,"Load prsnat.wlm"));
    FxNativeBootstrap api={.abi=1u,.bytes=sizeof(api),.request=direct,.publish=publish,.unpublish=unpublish};
    FxNativeExports exports={.abi=1u,.bytes=sizeof(exports)};
    assert(fenestra_native_entry(&api,&exports)==0 && exports.purpose==FX_MODULE_SERVICE && exports.notify);
    assert(fenestra_native_entry(&api,&exports)==FX_STATE);
    steps(160u);
    if(no_video) {
        assert(!(row(2u).flags&FX_UI_ENABLED) && !strcmp(row(4u).label,"Requires video core"));
        assert(exports.notify(exports.context,FX_RESIDENT_SHUTDOWN)==FX_OK);
        assert(fx_platform_stop(&native_owner,0u)==FX_OK);return 0;
    }
    assert(row(2u).kind==FX_UI_CHOICE && row(2u).option_count==5u && (row(2u).flags&FX_UI_ENABLED));
    assert(!strcmp(row(3u).text,"Stock") && !strcmp(row(4u).label,"Experimental"));
    assert(fx_ui_route(&ui_owner,2u,FX_INPUT_CHANGE,FX_VIDEO_LT)==FX_OK);busy_once=1u;steps(160u);
    assert(atomic_load(&policy.effective)==FX_VIDEO_LT && commits==1u && !strcmp(row(3u).text,"LT"));
    FxProviderLookup lookup={.name=FX_VIDEO_QUALITY_PROVIDER,.minimum=1u,.maximum=1u};FxProviderInfo info;
    assert(fx_provider_lookup(domain,&lookup,&info)==FX_OK);
    assert(select_other(info.token,FX_VIDEO_HQ)==FX_BUSY);
    assert(select_other(info.token,9u)==FX_ARGUMENT);
    assert(fx_ui_route(&ui_owner,2u,FX_INPUT_CHANGE,FX_VIDEO_STOCK)==FX_OK);steps(160u);
    assert(!atomic_load(&policy.effective) && !strcmp(row(3u).text,"Stock"));
    assert(select_other(info.token,FX_VIDEO_HQ)==FX_OK);steps(160u);
    assert(row(2u).value==FX_VIDEO_HQ && !strcmp(row(3u).text,"HQ"));
    assert(select_other(info.token,FX_VIDEO_PROXY)==FX_OK);idle=0u;
    assert(exports.notify(exports.context,FX_RESIDENT_SHUTDOWN)==FX_OK);
    FxServiceReply response={0};assert(fx_provider_call(domain,&ui_owner,info.token,FX_VIDEO_QUALITY_STATUS,0,0u,&response)==FX_STALE);
    assert(fx_platform_stop(&native_owner,0u)==FX_BUSY && atomic_load(&policy.effective)==FX_VIDEO_PROXY);
    idle=1u;assert(fx_platform_stop(&native_owner,0u)==FX_OK && !atomic_load(&policy.effective));
    steps(160u);assert(!(row(2u).flags&FX_UI_ENABLED) && !strcmp(row(4u).label,"Load prsnat.wlm"));
    return 0;
}
