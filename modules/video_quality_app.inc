/* Shared managed frontend for five-choice video services. */
enum {LIFE,OPEN,INFO,PAGE,CHOICE,STATUS_ROW,NOTE,MENU,EVENTS,SELECT,STATUS};
static FxSdkClient client;
static uint32_t phase,choice,polls,unavailable,menu_supported,status_dirty,persistent;
static uint32_t selection_waiting;
#ifdef FX_CHOICE_MODE_NOTE
static uint32_t selection_refused;
#endif
static uint64_t binding;
static FxVideoQualityStatus status;
static const char names[5][16]=FX_CHOICE_NAMES;
static void text(char *to,const char *from,uint32_t capacity) {
    uint32_t i=0u;while(i+1u<capacity && from[i]){to[i]=from[i];++i;}to[i]=0;
}
static FxResult control(const FxServiceModule *api,uint32_t id) {
    FxUiControl c={.abi=1u,.bytes=sizeof(c),.id=id,.parent=id==1u?0u:1u,
        .kind=id==1u?FX_UI_PAGE:id==2u?FX_UI_CHOICE:FX_UI_ACTION,
        .flags=FX_UI_VISIBLE|(id==1u || (id==2u && !unavailable)?FX_UI_ENABLED:0u)};
    if(id==1u){c.flags|=FX_UI_ROOT;text(c.label,FX_CHOICE_TITLE,sizeof(c.label));}
    if(id==2u) {
        c.value=choice;c.option_count=5u;text(c.label,FX_CHOICE_LABEL,sizeof(c.label));
        for(uint32_t i=0u;i<5u;++i)text(c.options[i],names[i],sizeof(c.options[i]));
    }
    if(id==3u) {
        text(c.label,"Effective",sizeof(c.label));
        const char *label=unavailable?"Unavailable":status.fault?"Needs restart":selection_waiting?"Selection busy":status.pending?"Waiting for idle":
            status.effective<=FX_VIDEO_PROXY?names[status.effective]:"Unavailable";
#ifdef FX_CHOICE_MODE_NOTE
        if (selection_refused && !status.fault) label = FX_CHOICE_MODE_NOTE;
#endif
        text(c.text,label,sizeof(c.text));
    }
    if(id==4u){text(c.label,unavailable?"Requires updated core":"Experimental",sizeof(c.label));text(c.text,unavailable?"Service unavailable":persistent?"Saved in camera":"Session only",sizeof(c.text));}
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
        else if(phase==MENU && (a.result==FX_CAPABILITY || a.result==FX_STATE)){phase=STATUS;}
#ifdef FX_CHOICE_MODE_NOTE
        else if(phase==SELECT && a.result==FX_STATE) {
            selection_refused=1u;selection_waiting=0u;status_dirty=1u;phase=STATUS;
        }
#endif
        else if(a.result==FX_BUSY){
            /* A rejected selection has no native commit. Read queued choices
             * before retrying so Stock can replace a request held by the fence. */
            if(phase==SELECT)phase=EVENTS;
        }
        else if(phase==EVENTS && (a.result==FX_OK || a.result==FX_EMPTY)) {
            if(a.result==FX_OK && a.bytes==sizeof(FxUiEvent)) {
                FxUiEvent e;for(uint32_t i=0u;i<sizeof(e);++i)((uint8_t *)&e)[i]=a.data[i];
                if(!unavailable && e.control==2u && e.event==FX_INPUT_CHANGE && e.value<=FX_VIDEO_PROXY){choice=e.value;selection_waiting=1u;status_dirty=1u;}
            }
            if(!unavailable && ++polls>=32u){polls=0u;phase=STATUS;}
            else if(a.result==FX_EMPTY && selection_waiting)phase=SELECT;
        } else if(a.result!=FX_OK)return 10+(int)phase;
        else if(phase==OPEN){binding=a.value[0];phase=INFO;}
        else if(phase==INFO) {
            if(a.bytes!=sizeof(FxVideoQualityInfo))return 4;
            FxVideoQualityInfo info;for(uint32_t i=0u;i<sizeof(info);++i)((uint8_t *)&info)[i]=a.data[i];
            if(info.abi!=FX_VIDEO_QUALITY_ABI || info.bytes!=sizeof(info) || info.family!=FX_CHOICE_FAMILY || info.choices!=31u)return 5;
            menu_supported=info.flags&FX_VIDEO_QUALITY_NATIVE_MENU;
            persistent=info.flags&FX_VIDEO_QUALITY_PERSISTENT;phase=PAGE;
        } else if(phase==STATUS) {
            if(a.bytes!=sizeof(status))return 6;
            FxVideoQualityStatus next;for(uint32_t i=0u;i<sizeof(next);++i)((uint8_t *)&next)[i]=a.data[i];
            if(next.abi!=1u || next.bytes!=sizeof(next) || next.family!=FX_CHOICE_FAMILY || next.effective>4u || next.requested>4u)return 7;
            uint32_t changed=status_dirty || next.effective!=status.effective || next.pending!=status.pending || next.fault!=status.fault;
            /* Status belongs to the admitted request. Keep a newer local choice
             * until SELECT accepts or refuses it. */
            uint32_t sync=!selection_waiting && next.requested!=choice;
            if(!selection_waiting)choice=next.requested;
            status_dirty=0u;status=next;phase=sync?CHOICE:changed?STATUS_ROW:EVENTS;
        } else if(phase==SELECT){
#ifdef FX_CHOICE_MODE_NOTE
            selection_refused=0u;
#endif
            selection_waiting=0u;status_dirty=1u;phase=STATUS;
        }
        else if(phase==STATUS_ROW)phase=status.abi?EVENTS:NOTE;
        else if(phase==NOTE)phase=unavailable?EVENTS:menu_supported?MENU:STATUS;
        else if(phase==MENU)phase=STATUS;
        else ++phase;
    }
    FxResult result;
    switch(phase) {
    case LIFE:result=fx_sdk_lifecycle(&client,api,FX_LIFE_CONFIGURE,FX_MODULE_EXTENSION);break;
    case OPEN:result=fx_sdk_open(&client,api,FX_CHOICE_PROVIDER,1u);break;
    case INFO:result=fx_sdk_platform(&client,api,FX_BIND_CALL,binding,FX_VIDEO_QUALITY_QUERY,0u,0,0u);break;
    case PAGE:result=control(api,1u);break;
    case CHOICE:result=control(api,2u);break;
    case STATUS_ROW:result=control(api,3u);break;
    case NOTE:result=control(api,4u);break;
    case MENU:result=fx_sdk_video_quality_menu(&client,api,binding,2u);break;
    case SELECT:result=fx_sdk_video_quality_select(&client,api,binding,FX_CHOICE_FAMILY,choice);break;
    case STATUS:result=fx_sdk_platform(&client,api,FX_BIND_CALL,binding,FX_VIDEO_QUALITY_STATUS,0u,0,0u);break;
    default:result=fx_sdk_events(&client,api);break;
    }
    return result==FX_OK?0:8;
}
