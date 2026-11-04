#include "fenestra_native_sdk.h"
#include "fenestra_video_quality.h"
#include "fenestra_memory.h"

static const FxNativeBootstrap *bootstrap;
static uint64_t backend,provider,client_owner;
static _Atomic uint32_t gate,stopping;

static FxResult backend_call(uint32_t operation,const void *data,uint32_t bytes,FxServiceReply *reply) {
    const uint64_t args[4]={FX_BIND_CALL,backend,operation,0u};
    return fx_native_request(bootstrap,FX_S_PLATFORM,args,data,bytes,reply);
}
static void copy_reply(FxServiceReply *to,const FxServiceReply *from) {
    to->bytes=from->bytes;
    memcpy(to->value,from->value,sizeof(to->value));
    if(from->bytes<=FX_SERVICE_BYTES)memcpy(to->data,from->data,from->bytes);
}
static void release_stock_client(const FxServiceReply *reply) {
    if(reply->bytes!=sizeof(FxVideoQualityStatus))return;
    FxVideoQualityStatus status;memcpy(&status,reply->data,sizeof(status));
    if(status.abi==1u && status.bytes==sizeof(status) && status.family==FX_VIDEO_FAMILY_PRORES422 &&
       !status.requested && !status.effective && !status.pending && !status.fault)client_owner=0u;
}
static FxResult call(void *context,const FxProviderClient *caller,uint64_t operation,
    const void *data,uint32_t bytes,FxServiceReply *reply) {
    (void)context;
    if(!caller || caller->abi!=1u || caller->bytes!=sizeof(*caller) || !caller->owner ||
       !caller->generation || !reply || (bytes && !data))return FX_ARGUMENT;
    uint32_t zero=0u;
    if(!atomic_compare_exchange_strong_explicit(&gate,&zero,1u,memory_order_acquire,memory_order_relaxed))return FX_BUSY;
    FxResult result=FX_ARGUMENT;FxServiceReply response={0};
    if(atomic_load_explicit(&stopping,memory_order_acquire)){result=FX_STATE;goto done;}
    if(!backend) {
        result=FX_CAPABILITY;
        if(operation==FX_VIDEO_QUALITY_QUERY && !bytes) {
            FxVideoQualityInfo info={1u,sizeof(info),1u,1u,
                FX_VIDEO_QUALITY_SESSION_ONLY|FX_VIDEO_QUALITY_EXPERIMENTAL|FX_VIDEO_QUALITY_UNAVAILABLE,0u};
            memcpy(reply->data,&info,sizeof(info));reply->bytes=sizeof(info);result=FX_OK;
        }
        goto done;
    }
    if((operation==FX_VIDEO_QUALITY_QUERY || operation==FX_VIDEO_QUALITY_STATUS) && !bytes) {
        result=backend_call((uint32_t)operation,0,0u,&response);
        if(result==FX_OK && operation==FX_VIDEO_QUALITY_STATUS)release_stock_client(&response);
    } else if(operation==FX_VIDEO_QUALITY_SELECT && bytes==sizeof(FxVideoQualitySelection)) {
        FxVideoQualitySelection choice;memcpy(&choice,data,sizeof(choice));
        if(choice.abi!=1u || choice.bytes!=sizeof(choice) || choice.family!=FX_VIDEO_FAMILY_PRORES422 ||
           choice.choice>FX_VIDEO_PROXY)goto done;
        uint64_t who=((uint64_t)caller->generation<<32)|caller->owner;
        if(client_owner && client_owner!=who){result=FX_BUSY;goto done;}
        result=backend_call(FX_VIDEO_QUALITY_SELECT,&choice,sizeof(choice),&response);
        if(result==FX_OK)client_owner=who;
    }
    if(result==FX_OK)copy_reply(reply,&response);
done:
    atomic_store_explicit(&gate,0u,memory_order_release);return result;
}
static FxResult notify(void *context,uint32_t event) {
    (void)context;(void)event;
    atomic_store_explicit(&stopping,1u,memory_order_release);
    if(!provider)return FX_OK;
    FxResult result=bootstrap->unpublish(bootstrap->context,provider);
    if(result==FX_OK)provider=0u;
    /* Core resource cleanup restores Stock after these calls drain. */
    return result;
}
int fenestra_native_entry(const FxNativeBootstrap *api,FxNativeExports *exports) {
    if(!api || api->abi!=FX_RESIDENT_ABI || api->bytes<sizeof(*api) || !api->request ||
       !api->publish || !api->unpublish || !exports || exports->abi!=FX_RESIDENT_ABI ||
       exports->bytes!=sizeof(*exports))return FX_CAPABILITY;
    if(bootstrap)return FX_STATE;
    bootstrap=api;exports->purpose=FX_MODULE_SERVICE;exports->notify=notify;
    const uint64_t args[4]={FX_BIND_OPEN,1u,0u,0u};
    char name[64]=FX_VIDEO_QUALITY_PROVIDER;FxServiceReply reply={0};
    FxResult result=fx_native_request(api,FX_S_PLATFORM,args,name,sizeof(name),&reply);
    if(result!=FX_CAPABILITY && result!=FX_STATE) {
        if(result!=FX_OK)return (int)result;
        backend=reply.value[0];
        result=backend_call(FX_VIDEO_QUALITY_QUERY,0,0u,&reply);
        if(result!=FX_OK)return (int)result;
        if(reply.bytes!=sizeof(FxVideoQualityInfo))return FX_INTEGRITY;
        FxVideoQualityInfo info;memcpy(&info,reply.data,sizeof(info));
        if(info.abi!=1u || info.bytes!=sizeof(info) || info.family!=FX_VIDEO_FAMILY_PRORES422 ||
           info.choices!=31u || !(info.flags&FX_VIDEO_QUALITY_SESSION_ONLY))return FX_INTEGRITY;
    }
    FxProviderDeclaration declaration={.name=FX_VIDEO_QUALITY_PROVIDER,.version=1u,.call=call};
    return (int)api->publish(api->context,&declaration,&provider);
}
