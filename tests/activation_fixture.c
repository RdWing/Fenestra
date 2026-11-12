#include "fenestra_activation.h"
#include <assert.h>
#include <string.h>
typedef struct {uint32_t words[4],checks,writes,syncs,fail_check,fail_write,fail_sync,steal;} Model;
static FxResult check(void *p,const FxActivationWord *r) {
    Model *m=p;assert(r->site<16u);return ++m->checks==m->fail_check?FX_CAPABILITY:FX_OK;
}
static uint32_t read_word(void *p,const FxActivationWord *r){return ((Model *)p)->words[r->site/4u];}
static FxResult exchange(void *p,const FxActivationWord *r,uint32_t old,uint32_t next) {
    Model *m=p;uint32_t *w=&m->words[r->site/4u];
    if(++m->writes==m->fail_write){if(m->steal)*w=99u;return FX_BUSY;}
    if(*w!=old)return FX_INTEGRITY;
    *w=next;return FX_OK;
}
static FxResult sync_words(void *p,const FxActivationWord *r) {
    (void)r;Model *m=p;return ++m->syncs==m->fail_sync?FX_IO:FX_OK;
}
int main(void) {
    const FxActivationWord rows[]={{0,10,20},{4,11,21},{8,12,22},{12,13,23}};
    Model model={.words={10,11,12,13}};FxActivationMemory memory={&model,check,read_word,exchange,sync_words};
    uint64_t owned=0;
    assert(fx_activation_install(rows,0,&memory,0,&owned)==FX_OK && !owned && !model.writes);
    assert(fx_activation_restore(rows,0,&memory,&owned)==FX_OK && !owned && !model.writes);
    assert(fx_activation_install(rows,4,&memory,0,&owned)==FX_OK && owned==15);
    assert(fx_activation_restore(rows,4,&memory,&owned)==FX_OK && !owned);
    for(unsigned n=1;n<=4;++n) {
        model=(Model){{10,11,12,13},.fail_check=n};owned=0;
        assert(fx_activation_install(rows,4,&memory,0,&owned)==FX_CAPABILITY && !owned && !model.writes);
        model=(Model){{10,11,12,13},.fail_write=n};owned=0;
        assert(fx_activation_install(rows,4,&memory,0,&owned)==FX_BUSY && !owned);
        for(unsigned i=0;i<4;++i)assert(model.words[i]==10+i);
        model=(Model){{10,11,12,13},.fail_sync=n};owned=0;
        assert(fx_activation_install(rows,4,&memory,0,&owned)==FX_IO && !owned);
        for(unsigned i=0;i<4;++i)assert(model.words[i]==10+i);
    }
    model=(Model){.words={20,21,22,23}};owned=0;
    assert(fx_activation_install(rows,4,&memory,0,&owned)==FX_INTEGRITY && !model.writes);
    assert(fx_activation_install(rows,4,&memory,1,&owned)==FX_OK && owned==15 && !model.writes);
    model.words[1]=99;
    assert(fx_activation_restore(rows,4,&memory,&owned)==FX_INTEGRITY && owned==2 && model.words[1]==99);
    model=(Model){.words={20,11,22,13}};owned=0;
    assert(fx_activation_install(rows,4,&memory,1,&owned)==FX_OK && owned==15 && model.writes==2);
    model.fail_write=model.writes+2;
    assert(fx_activation_restore(rows,4,&memory,&owned)==FX_BUSY && owned==4);
    assert(fx_activation_restore(rows,4,&memory,&owned)==FX_OK && !owned);
    _Atomic uint32_t latch=FX_ACT_CLEAN;
    assert(fx_activation_claim(&latch,0)==FX_OK && latch==FX_ACT_MODIFIED);
    assert(fx_activation_claim(&latch,0)==FX_STATE);
    assert(fx_activation_claim(&latch,1)==FX_OK);
    latch=FX_ACT_UPDATE;assert(fx_activation_claim(&latch,1)==FX_STATE);
    latch=3;assert(fx_activation_claim(&latch,1)==FX_STATE);
    return 0;
}
