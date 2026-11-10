#include "color_job.h"
#include "fenestra_memory.h"

static uint16_t u16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0]|(uint16_t)((uint16_t)p[1]<<8));
}
static uint32_t u32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static uint64_t u64(const uint8_t *p) {
    return (uint64_t)u32(p)|((uint64_t)u32(p+4)<<32);
}
static int bounded(const void *p,size_t n,size_t minimum) {
    return p && n>=minimum && n<=UINTPTR_MAX-(uintptr_t)p;
}
static int separate(const void *a,size_t an,const void *b,size_t bn) {
    uintptr_t av=(uintptr_t)a,bv=(uintptr_t)b;
    return an<=UINTPTR_MAX-av && bn<=UINTPTR_MAX-bv && (av+an<=bv || bv+bn<=av);
}
static int valid(const FxZ63ColorJobView *v) {
    if(!v || !bounded(v->job,v->job_bytes,FX_Z63_COLOR_JOB_BYTES) ||
        !bounded(v->context,v->context_bytes,FX_Z63_COLOR_CONTEXT_BYTES) ||
        !bounded(v->frame,v->frame_bytes,FX_Z63_COLOR_FRAME_BYTES) ||
        !bounded(v->generator_input,v->generator_input_bytes,0x40) ||
        !bounded(v->generator_output,v->generator_output_bytes,8))return 0;
    const uint8_t *j=v->job,*c=v->context,*i=v->generator_input,*o=v->generator_output;
    return u64(j+0x10)==(uintptr_t)c && u64(c+0xa58)==(uintptr_t)v->frame &&
        u64(i+8)==(uintptr_t)v->frame && u64(i+0x10)==(uintptr_t)j+0x1fe8 &&
        u64(i+0x18)==(uintptr_t)j+0x410 && u32(i)==u32(j) &&
        u64(o)==(uintptr_t)j+FX_Z63_COLOR_GENERATOR_OUTPUT;
}
uint16_t fx_z63_color_job_interpolate(uint16_t value,uint16_t weight) {
    uint32_t product=(uint32_t)(((int64_t)value-1024)*(int64_t)weight);
    uint32_t sum=product+262144u;
    int64_t signed_sum=(int64_t)sum-((sum&0x80000000u)?INT64_C(4294967296):0);
    int64_t scalar;
    if((product+0x40040000u)&0x80000000u)scalar=signed_sum/256;
    else scalar=signed_sum<0?-((-signed_sum+128)/256):(signed_sum+128)/256;
    return (uint16_t)scalar;
}
int fx_z63_color_job_style(const FxZ63ColorJobView *view) {
    if(!valid(view))return -1;
    uint32_t style=u32((const uint8_t *)view->job+0x9c+0x118);
    return (style&0x80000000u)?0:(style>37u?37:(int)style);
}
int fx_z63_color_job_apply(const FxZ63ColorJobView *v,int selected,
    const uint16_t *chroma_lut,size_t chroma_values,
    const uint16_t *curve,size_t knots,FxZ63ColorCandidate *workspace) {
    if(selected==0)return FX_Z63_COLOR_JOB_STOCK;
    if(selected!=1 || !valid(v) || v->generator_result!=1 || !workspace || !chroma_lut || !curve ||
        chroma_values<25u || chroma_values>SIZE_MAX/sizeof(*chroma_lut) || knots!=229u)
        return FX_Z63_COLOR_JOB_INVALID;
    uint8_t *j=v->job;
    const uint8_t *c=v->context,*f=v->frame,*prepared=j+0x9c;
    uint32_t file=u32(f+0x3a4),class_id=u32(c+0x10);
    if(j[4] || c[0x1b] || !c[0x51] || !c[0x54] || c[0x55] ||
        (class_id!=6u && class_id!=7u) || u32(f)!=1u || u32(f+4) ||
        f[0x618] || f[0x2cd8] || (file!=3u && file!=4u) ||
        u32(prepared+0xb8)!=1u || prepared[0x109] || prepared[0x111])
        return FX_Z63_COLOR_JOB_UNSUPPORTED;
    if(!separate(workspace,sizeof(*workspace),v,sizeof(*v)) ||
        !separate(workspace,sizeof(*workspace),j,v->job_bytes) ||
        !separate(workspace,sizeof(*workspace),c,v->context_bytes) ||
        !separate(workspace,sizeof(*workspace),f,v->frame_bytes) ||
        !separate(workspace,sizeof(*workspace),v->generator_input,v->generator_input_bytes) ||
        !separate(workspace,sizeof(*workspace),v->generator_output,v->generator_output_bytes) ||
        !separate(workspace,sizeof(*workspace),chroma_lut,chroma_values*sizeof(*chroma_lut)) ||
        !separate(workspace,sizeof(*workspace),curve,knots*sizeof(*curve)))
        return FX_Z63_COLOR_JOB_INVALID;
    size_t index=prepared[0x125]<24u?prepared[0x125]:24u;
    uint16_t scalar=fx_z63_color_job_interpolate(chroma_lut[index],u16(prepared+0x126));
    if(!fx_z63_color_transplant(workspace,j+FX_Z63_COLOR_PARAMETERS,sizeof(workspace->parameters),
        j+FX_Z63_COLOR_PACKED_SAMPLES,sizeof(workspace->samples),curve,knots,scalar))
        return FX_Z63_COLOR_JOB_INVALID;
    memcpy(j+FX_Z63_COLOR_PARAMETERS,workspace->parameters,sizeof(workspace->parameters));
    memcpy(j+FX_Z63_COLOR_PACKED_SAMPLES,workspace->samples,sizeof(workspace->samples));
    return FX_Z63_COLOR_JOB_APPLIED;
}
