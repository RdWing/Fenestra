#include "color_transplant.h"
#include "fenestra_memory.h"

static int disjoint(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t av=(uintptr_t)a,bv=(uintptr_t)b;
    if(an>UINTPTR_MAX-av || bn>UINTPTR_MAX-bv)return 0;
    return av+an<=bv || bv+bn<=av;
}
static void put16(uint8_t *p,uint16_t v) {
    p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);
}
int fx_z63_color_transplant(FxZ63ColorCandidate *output,
    const void *parameters,size_t parameter_bytes,const void *samples,size_t sample_bytes,
    const uint16_t *curve,size_t knots,uint16_t chroma_q10) {
    static const int16_t m2[9]={200,310,3,-65,-504,569,480,-484,4};
    static const size_t offsets[6]={0xbe6,0xdb0,0xf7a,0x1144,0x130e,0x14d8};
    const uint8_t *p=(const uint8_t *)parameters;
    if(!output || !parameters || !samples || !curve ||
        parameter_bytes!=sizeof(output->parameters) || sample_bytes!=sizeof(output->samples) ||
        knots!=229u)return 0;
    if(!disjoint(output,sizeof(*output),parameters,parameter_bytes) ||
        !disjoint(output,sizeof(*output),samples,sample_bytes) ||
        !disjoint(output,sizeof(*output),curve,knots*sizeof(*curve)))return 0;
    /* These are the two tone-dependent controls in the checked ordinary
     * serializer. Refuse other source configurations before copying any data. */
    if(p[0x263]!=2u || p[0x264]!=2u)return 0;
    for(size_t i=0;i<knots;i++) {
        if(curve[i]>32767u || (i && curve[i]<curve[i-1u]))return 0;
    }
    memcpy(output->parameters,parameters,parameter_bytes);
    memcpy(output->samples,samples,sample_bytes);
    for(size_t i=0;i<9u;i++) {
        int32_t v=m2[i];
        if(i>=3u) {
            v*=chroma_q10;
            v=v<0?-((-v+512)/1024):(v+512)/1024;
        }
        put16(output->parameters+0x248+2u*i,(uint16_t)v);
    }
    output->parameters[0x263]=3u;output->parameters[0x264]=3u;
    for(size_t bank=0;bank<6u;bank++)
        for(size_t i=0;i<knots;i++)put16(output->samples+offsets[bank]+2u*i,curve[i]);
    /* The separate Nlg table at +0x16A2 stays on the supplied N-Log row.
     * Original ZR tone 3 uses that row, not a rounded Log3G10 vector. */
    return 1;
}

int fx_z63_color_rwg_candidate(FxZ63ColorCandidate *output,
    const void *parameters,size_t parameter_bytes,const void *samples,size_t sample_bytes,
    const int16_t *m1_q10,size_t coefficients,const uint16_t *curve,size_t knots) {
    static const int16_t m2[9]={109,366,37,-59,-197,256,256,-233,-23};
    static const int16_t cpxs[6]={253,-28,-19,252,26,50};
    static const size_t offsets[6]={0xbe6,0xdb0,0xf7a,0x1144,0x130e,0x14d8};
    const uint8_t *p=parameters;
    if(!output || !parameters || !samples || !m1_q10 || !curve ||
        parameter_bytes!=sizeof(output->parameters) || sample_bytes!=sizeof(output->samples) ||
        coefficients!=9u || knots!=229u)return 0;
    if(!disjoint(output,sizeof(*output),parameters,parameter_bytes) ||
        !disjoint(output,sizeof(*output),samples,sample_bytes) ||
        !disjoint(output,sizeof(*output),m1_q10,9u*sizeof(*m1_q10)) ||
        !disjoint(output,sizeof(*output),curve,229u*sizeof(*curve)))return 0;
    if(p[0x1e8] || p[0x1e9] || p[0x263]!=2u || p[0x264]!=2u)return 0;
    for(size_t i=0;i<9u;i++)if(m1_q10[i]<-4096 || m1_q10[i]>4095)return 0;
    /* Rounded NLG must fit twelve bits. 32764 would round to 4096 and the
     * native low-bit writer would encode zero at the highlight endpoint. */
    for(size_t i=0;i<knots;i++)
        if(curve[i]>32763u || (i && curve[i]<curve[i-1u]))return 0;
    memcpy(output->parameters,parameters,parameter_bytes);
    memcpy(output->samples,samples,sample_bytes);
    for(size_t i=0;i<9u;i++) {
        put16(output->parameters+0x1eau+2u*i,(uint16_t)m1_q10[i]);
        put16(output->parameters+0x248u+2u*i,(uint16_t)m2[i]);
    }
    for(size_t field=0;field<6u;field++)
        for(size_t bank=0;bank<2u;bank++)
            for(size_t node=0;node<32u;node++)
                put16(output->samples+64u*(2u*field+bank)+2u*node,(uint16_t)cpxs[field]);
    for(size_t i=0;i<knots;i++) {
        for(size_t bank=0;bank<6u;bank++)
            put16(output->samples+offsets[bank]+2u*i,curve[i]);
        put16(output->samples+0x16a2u+2u*i,(uint16_t)(((uint32_t)curve[i]+4u)/8u));
    }
    return 1;
}
