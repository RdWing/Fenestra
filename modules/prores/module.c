/* The module owns the page and selection policy. Native pointers, instructions
 * and camera addresses belong only to the target adapter. Session-only v1. */
#include "fenestra_video_quality_sdk.h"
enum {LIFE,OPEN,FIND,INFO,PAGE,CHOICE,STATUS_ROW,NOTE,EVENTS,SELECT,STATUS};
static FxSdkClient client;
static uint32_t phase,choice,polls,unavailable,page_created,backend_missing;
static uint64_t binding,provider;
static FxVideoQualityStatus status;
static const char names[5][16]={"Stock","HQ","Standard","LT","Proxy"};
static void text(char *to,const char *from,uint32_t capacity) {
    uint32_t i=0u;while(i+1u<capacity && from[i]){to[i]=from[i];++i;}to[i]=0;
}
static FxResult control(const FxServiceModule *api,uint32_t id) {
    FxUiControl c={.abi=1u,.bytes=sizeof(c),.id=id,.parent=id==1u?0u:1u,
        .kind=id==1u?FX_UI_PAGE:id==2u?FX_UI_CHOICE:FX_UI_ACTION,
        .flags=FX_UI_VISIBLE|(id==1u || (id==2u && !unavailable)?FX_UI_ENABLED:0u)};
    if(id==1u){c.flags|=FX_UI_ROOT;text(c.label,"ProRes quality",sizeof(c.label));}
    if(id==2u) {
        c.value=choice;c.option_count=5u;text(c.label,"Quality",sizeof(c.label));
        for(uint32_t i=0u;i<5u;++i)text(c.options[i],names[i],sizeof(c.options[i]));
    }
    if(id==3u) {
        text(c.label,"Effective",sizeof(c.label));
        const char *label=unavailable?"Unavailable":status.fault?"Needs restart":status.pending?"Waiting for idle":
            status.effective<=FX_VIDEO_PROXY?names[status.effective]:"Unavailable";
        text(c.text,label,sizeof(c.text));
    }
    if(id==4u){text(c.label,backend_missing?"Requires video core":unavailable?(binding?"Load prsnat.wlm":"Requires updated core"):"Experimental",sizeof(c.label));text(c.text,"Session only",sizeof(c.text));}
    return fx_sdk_ui(&client,api,&c);
}
int fenestra_module_entry(const FxModuleServices *base) {
    if(!base || base->bytes!=sizeof(FxServiceModule))return 1;
    const FxServiceModule *api=(const FxServiceModule *)base;
    if(api->service_abi!=FX_SERVICE_ABI || !api->exchange)return 2;
    if(client.pending) {
        FxServiceReply a;FxResult taken=fx_sdk_take(&client,api,&a);
        if(taken==FX_BUSY)return 0;if(taken!=FX_OK)return 3;
        if(phase==OPEN && (a.result==FX_CAPABILITY || a.result==FX_STATE)){unavailable=1u;phase=PAGE;}
        else if(phase==FIND && a.result==FX_EMPTY){unavailable=1u;phase=page_created?CHOICE:PAGE;}
        else if((phase==INFO || phase==STATUS || phase==SELECT) && a.result==FX_STALE){
            unavailable=1u;provider=0u;status=(FxVideoQualityStatus){0};phase=CHOICE;
        }
        else if(a.result==FX_BUSY){ /* Retry this stage without duplicating a commit. */ }
        else if(phase==EVENTS && (a.result==FX_OK || a.result==FX_EMPTY)) {
            if(a.result==FX_OK && a.bytes==sizeof(FxUiEvent)) {
                FxUiEvent e;for(uint32_t i=0u;i<sizeof(e);++i)((uint8_t *)&e)[i]=a.data[i];
                if(!unavailable && e.control==2u && e.event==FX_INPUT_CHANGE && e.value<=FX_VIDEO_PROXY){choice=e.value;phase=SELECT;}
            }
            if(phase==EVENTS && ++polls>=32u){polls=0u;if(binding && !backend_missing)phase=unavailable?FIND:STATUS;}
        } else if(a.result!=FX_OK)return 10+(int)phase;
        else if(phase==OPEN){binding=a.value[0];phase=FIND;}
        else if(phase==FIND) {
            if(a.bytes!=sizeof(FxProviderInfo))return 9;
            FxProviderInfo info;for(uint32_t i=0u;i<sizeof(info);++i)((uint8_t *)&info)[i]=a.data[i];
            if(!info.token || info.version!=1u || !info.active)return 9;
            provider=info.token;unavailable=backend_missing=0u;status=(FxVideoQualityStatus){0};phase=INFO;
        }
        else if(phase==INFO) {
            if(a.bytes!=sizeof(FxVideoQualityInfo))return 4;
            FxVideoQualityInfo info;for(uint32_t i=0u;i<sizeof(info);++i)((uint8_t *)&info)[i]=a.data[i];
            if(info.abi!=FX_VIDEO_QUALITY_ABI || info.bytes!=sizeof(info) || info.family!=FX_VIDEO_FAMILY_PRORES422)return 5;
            backend_missing=(info.flags&FX_VIDEO_QUALITY_UNAVAILABLE)!=0u;
            if(info.choices!=(backend_missing?1u:31u))return 5;
            if(backend_missing)unavailable=1u;
            phase=page_created?CHOICE:PAGE;
        } else if(phase==STATUS) {
            if(a.bytes!=sizeof(status))return 6;
            FxVideoQualityStatus next;for(uint32_t i=0u;i<sizeof(next);++i)((uint8_t *)&next)[i]=a.data[i];
            if(next.abi!=1u || next.bytes!=sizeof(next) || next.family!=1u || next.effective>4u || next.requested>4u)return 7;
            uint32_t changed=next.effective!=status.effective || next.pending!=status.pending || next.fault!=status.fault;
            uint32_t sync=next.requested!=choice;choice=next.requested;
            status=next;phase=sync?CHOICE:changed?STATUS_ROW:EVENTS;
        } else if(phase==SELECT)phase=STATUS;
        else if(phase==PAGE){page_created=1u;phase=CHOICE;}
        else if(phase==STATUS_ROW)phase=status.abi?EVENTS:NOTE;
        else if(phase==NOTE)phase=unavailable?EVENTS:STATUS;
        else ++phase;
    }
    FxResult result;
    switch(phase) {
    case LIFE:result=fx_sdk_lifecycle(&client,api,FX_LIFE_CONFIGURE,FX_MODULE_EXTENSION);break;
    case OPEN:result=fx_sdk_open(&client,api,"core.providers",1u);break;
    case FIND:result=fx_sdk_provider_find(&client,api,binding,FX_VIDEO_QUALITY_PROVIDER,1u,1u,0u);break;
    case INFO:result=fx_sdk_provider_call(&client,api,binding,provider,FX_VIDEO_QUALITY_QUERY,0,0u);break;
    case PAGE:result=control(api,1u);break;
    case CHOICE:result=control(api,2u);break;
    case STATUS_ROW:result=control(api,3u);break;
    case NOTE:result=control(api,4u);break;
    case SELECT:result=fx_sdk_video_quality_provider_select(&client,api,binding,provider,FX_VIDEO_FAMILY_PRORES422,choice);break;
    case STATUS:result=fx_sdk_provider_call(&client,api,binding,provider,FX_VIDEO_QUALITY_STATUS,0,0u);break;
    default:result=fx_sdk_events(&client,api);break;
    }
    return result==FX_OK?0:8;
}
