#include <assert.h>
#include <string.h>
#include "../modules/prores/module.c"
static FxServiceExchange exchange;
static FxServiceModule api={.base={.bytes=sizeof(FxServiceModule)},.service_abi=FX_SERVICE_ABI,.exchange=&exchange};
static FxUiControl rows[5];
static uint32_t absent,inject,selected,queries,commits,busy_once;
static void step(void) {
    assert(fenestra_module_entry(&api.base)==0);
    FxServiceRequest *q=&exchange.request;FxServiceReply *a=&exchange.reply;
    *a=(FxServiceReply){.sequence=q->sequence,.result=FX_OK};
    if(q->operation==FX_S_LIFECYCLE)return;
    if(q->operation==FX_S_PLATFORM) {
        if(q->arg[0]==FX_BIND_OPEN) {
            assert(!strcmp((char *)q->data,"camera.video.quality") && q->arg[1]==1u);
            if(absent)a->result=FX_CAPABILITY;else a->value[0]=101u;
        } else {
            assert(!absent && q->arg[0]==FX_BIND_CALL && q->arg[1]==101u);
            if(q->arg[2]==FX_VIDEO_QUALITY_QUERY) {
                FxVideoQualityInfo info={1u,sizeof(info),1u,31u,3u,0u};
                a->bytes=sizeof(info);memcpy(a->data,&info,sizeof(info));
            } else if(q->arg[2]==FX_VIDEO_QUALITY_STATUS) {
                FxVideoQualityStatus s={1u,sizeof(s),1u,selected,selected,1u,0u,0u,0u,0u,commits,0u};
                a->bytes=sizeof(s);memcpy(a->data,&s,sizeof(s));++queries;
            } else {
                assert(q->arg[2]==FX_VIDEO_QUALITY_SELECT && q->bytes==sizeof(FxVideoQualitySelection));
                FxVideoQualitySelection s;memcpy(&s,q->data,sizeof(s));
                assert(s.abi==1u && s.bytes==sizeof(s) && s.family==1u && s.choice<5u);
                if(busy_once){a->result=FX_BUSY;busy_once=0u;}
                else {selected=s.choice;++commits;}
            }
        }
    } else {
        assert(q->operation==FX_S_UI);
        if(q->arg[0]==FX_UI_PUT) {
            FxUiControl c;memcpy(&c,q->data,sizeof(c));assert(c.id>=1u && c.id<=4u);rows[c.id]=c;
        } else {
            assert(q->arg[0]==FX_UI_POLL);
            if(inject) {
                FxUiEvent e={1u,2u,FX_INPUT_CHANGE,inject-1u,1u};inject=0u;
                a->bytes=sizeof(e);memcpy(a->data,&e,sizeof(e));
            } else a->result=FX_EMPTY;
        }
    }
}
int main(void) {
    for(uint32_t i=0u;i<100u;++i)step();
    assert(rows[1].kind==FX_UI_PAGE && !strcmp(rows[1].label,"ProRes quality"));
    assert(rows[2].kind==FX_UI_CHOICE && rows[2].option_count==5u && rows[2].value==0u);
    assert(!strcmp(rows[3].text,"Stock") && queries && !commits);
    inject=FX_VIDEO_LT+1u;busy_once=1u;
    for(uint32_t i=0u;i<100u;++i)step();
    assert(selected==FX_VIDEO_LT && commits==1u && !strcmp(rows[3].text,"LT"));
    inject=FX_VIDEO_STOCK+1u;
    for(uint32_t i=0u;i<100u;++i)step();
    assert(!selected && commits==2u && !strcmp(rows[3].text,"Stock"));
    client=(FxSdkClient){0};phase=choice=polls=unavailable=0u;binding=0u;status=(FxVideoQualityStatus){0};
    memset(&exchange,0,sizeof(exchange));memset(rows,0,sizeof(rows));absent=1u;
    for(uint32_t i=0u;i<100u;++i)step();
    assert(!(rows[2].flags&FX_UI_ENABLED) && !strcmp(rows[3].text,"Unavailable"));
    assert(!strcmp(rows[4].label,"Requires updated core"));
    return 0;
}
