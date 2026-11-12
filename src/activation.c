#include "fenestra_activation.h"
#include "fenestra_memory.h"
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
FxResult fx_activation_record(const uint8_t *p,uint32_t bytes,const uint8_t build[32]) {
    if(!p || !build)return FX_ARGUMENT;
    if(bytes!=64u || memcmp(p,"FX63ARM1",8u) || memcmp(p+8,build,32u))return FX_INTEGRITY;
    /* v1 has one supported feature set and manual cold-start activation. */
    if(u32(p+40)!=1u)return FX_CAPABILITY;
    for(uint32_t i=44u;i<60u;++i)if(p[i])return FX_INTEGRITY;
    uint32_t c=UINT32_MAX;
    for(uint32_t i=0;i<60u;++i) {
        c^=p[i];for(uint32_t bit=0;bit<8u;++bit)c=(c>>1)^((0u-(c&1u))&UINT32_C(0xedb88320));
    }
    return u32(p+60)==~c?FX_OK:FX_INTEGRITY;
}
FxResult fx_activation_claim(_Atomic uint32_t *latch,int resume) {
    if(!latch)return FX_ARGUMENT;
    uint32_t clean=FX_ACT_CLEAN;
    if(atomic_compare_exchange_strong_explicit(latch,&clean,FX_ACT_MODIFIED,
                                              memory_order_acq_rel,memory_order_acquire))return FX_OK;
    return resume && clean==FX_ACT_MODIFIED?FX_OK:FX_STATE;
}
static int valid(const FxActivationWord *rows,uint32_t count,const FxActivationMemory *m) {
    if(!rows || count>40u || !m || !m->check || !m->read || !m->exchange || !m->sync)return 0;
    for(uint32_t i=0;i<count;++i) {
        if((rows[i].site&3u) || rows[i].original==rows[i].replacement)return 0;
        for(uint32_t j=0;j<i;++j)if(rows[i].site==rows[j].site)return 0;
    }
    return 1;
}
FxResult fx_activation_restore(const FxActivationWord *rows,uint32_t count,const FxActivationMemory *m,uint64_t *owned) {
    if(!owned || !valid(rows,count,m) || (*owned>>count))return FX_ARGUMENT;
    FxResult result=FX_OK;
    for(uint32_t i=count;i>0u;--i) {
        uint32_t j=i-1u;uint64_t bit=UINT64_C(1)<<j;
        if(!(*owned&bit))continue;
        FxResult r=m->check(m->context,&rows[j]);
        if(r==FX_OK) {
            uint32_t actual=m->read(m->context,&rows[j]);
            if(actual==rows[j].original)r=m->sync(m->context,&rows[j]);
            else if(actual!=rows[j].replacement)r=FX_INTEGRITY;
            else {
                r=m->exchange(m->context,&rows[j],rows[j].replacement,rows[j].original);
                if(r==FX_OK)r=m->sync(m->context,&rows[j]);
            }
        }
        if(r==FX_OK)*owned&=~bit;
        else result=r; /* Keep uncertain records owned and never overwrite a peer. */
    }
    return result;
}
FxResult fx_activation_install(const FxActivationWord *rows,uint32_t count,const FxActivationMemory *m,int resume,uint64_t *owned) {
    if(!owned || *owned || !valid(rows,count,m))return FX_ARGUMENT;
    /* Validate the complete set before writing a single word. Retained words
     * are accepted only after the caller proves the same build's wake state. */
    for(uint32_t i=0;i<count;++i) {
        FxResult r=m->check(m->context,&rows[i]);if(r!=FX_OK)return r;
        uint32_t word=m->read(m->context,&rows[i]);
        if(word!=rows[i].original && !(resume && word==rows[i].replacement))return FX_INTEGRITY;
    }
    for(uint32_t i=0;i<count;++i) {
        uint64_t bit=UINT64_C(1)<<i;FxResult r=FX_OK;
        uint32_t actual=m->read(m->context,&rows[i]);
        if(actual==rows[i].replacement && resume)*owned|=bit;
        else {
            r=m->check(m->context,&rows[i]);
            if(r==FX_OK)r=m->exchange(m->context,&rows[i],rows[i].original,rows[i].replacement);
            if(r==FX_OK)*owned|=bit;
        }
        if(r==FX_OK)r=m->sync(m->context,&rows[i]);
        if(r!=FX_OK) {
            FxResult rollback=fx_activation_restore(rows,count,m,owned);
            return rollback==FX_OK?r:rollback;
        }
    }
    return FX_OK;
}
