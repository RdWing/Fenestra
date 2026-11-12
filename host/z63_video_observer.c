/* Read-only C2.01 video lifetime observations. Model input, never a hook,
 * completion injector or physical-camera transport. */
#include <qemu-plugin.h>
#include <glib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
QEMU_PLUGIN_EXPORT int qemu_plugin_version=QEMU_PLUGIN_VERSION;
static struct qemu_plugin_register *registers[16][32];
static FILE *output;
static GMutex mutex;
static uint64_t record_offset;
static const uint64_t points[]={0x40707038,0x40756018,0x4075604c,0x40756050,0x40d26db0,0x40759c00,0x40758158,0x4075815c,
    0x402fbe64,0x402fd5ac,0x402fd868,0x402fd878,0x40356370,
    0x40e7fd08,0x40e80c74,0x40e80fcc,0x40d22770,0x40755a54};
static uint64_t counts[G_N_ELEMENTS(points)],sequence;
static uint64_t value(unsigned cpu,unsigned index) {
    g_autoptr(GByteArray) bytes=g_byte_array_new();uint64_t result=0;
    if(!registers[cpu][index] || qemu_plugin_read_register(registers[cpu][index],bytes)!=8 || bytes->len!=8)return 0;
    memcpy(&result,bytes->data,8);return GUINT64_FROM_LE(result);
}
static void memory(const char *name,uint64_t address,unsigned size) {
    fprintf(output,",\"%s\":",name);
    if(address<UINT64_C(0xa00000000) || address>UINT64_C(0xa40000000)-size) {fputs("null",output);return;}
    g_autoptr(GByteArray) bytes=g_byte_array_new();
    if(!qemu_plugin_read_memory_vaddr(address,bytes,size) || bytes->len!=size) {fputs("null",output);return;}
    fputc('"',output);for(unsigned i=0;i<size;++i)fprintf(output,"%02x",bytes->data[i]);fputc('"',output);
}
static uint64_t read64(uint64_t address) {
    uint64_t result=0;g_autoptr(GByteArray) bytes=g_byte_array_new();
    if(address<UINT64_C(0xa00000000) || address>UINT64_C(0xa40000000)-8 ||
       !qemu_plugin_read_memory_vaddr(address,bytes,8) || bytes->len!=8)return 0;
    memcpy(&result,bytes->data,8);return GUINT64_FROM_LE(result);
}
static void observe(unsigned cpu,void *context) {
    unsigned index=(unsigned)(uintptr_t)context;
    if(cpu>=16 || !registers[cpu][0])return;
    g_mutex_lock(&mutex);uint64_t ordinal=++counts[index];
    if(ordinal<=64) {
        fprintf(output,"{\"kind\":\"call\",\"sequence\":%"PRIu64",\"pc\":\"0x%"PRIx64"\",\"cpu\":%u,\"ordinal\":%"PRIu64,
                sequence++,points[index],cpu,ordinal);
        static const unsigned selected[]={0,1,2,3,8,19,20,21,22,23,24,25,26,27,28,29,30,31};
        for(unsigned j=0;j<G_N_ELEMENTS(selected);++j) {
            unsigned n=selected[j];fprintf(output,",\"r%u\":\"0x%"PRIx64"\"",n,value(cpu,n));
        }
        memory("arg0",value(cpu,0),0x120);memory("arg1",value(cpu,1),0xc0);
        memory("stack",value(cpu,31),512);
        memory("capture",UINT64_C(0xa048bb044),4);memory("movie",UINT64_C(0xa03324ce0),4);
        memory("outstanding",UINT64_C(0xa03324dc8),4);memory("pipeline",UINT64_C(0xa03d42100),12);
        uint64_t source=read64(UINT64_C(0xa048bb3b0));
        fprintf(output,",\"capture_source\":\"0x%"PRIx64"\"",source);
        memory("source_request",source,0x110);
        if(record_offset) {
            uint64_t state=read64(UINT64_C(0xa02912e60));
            if((read64(state+64)&UINT32_MAX)==UINT32_C(0x465a634d))memory("recording",state+record_offset,32);
        }
        fputs("}\n",output);fflush(output);
    }
    g_mutex_unlock(&mutex);
}
static void initialize(qemu_plugin_id_t id,unsigned cpu) {
    (void)id;if(cpu>=16)return;
    g_autoptr(GArray) available=qemu_plugin_get_registers();
    for(unsigned i=0;i<available->len;++i) {
        qemu_plugin_reg_descriptor *r=&g_array_index(available,qemu_plugin_reg_descriptor,i);
        for(unsigned n=0;n<31;++n) {char key[8];snprintf(key,sizeof(key),"x%u",n);if(!strcmp(key,r->name))registers[cpu][n]=r->handle;}
        if(!strcmp(r->name,"sp"))registers[cpu][31]=r->handle;
    }
}
static void translate(qemu_plugin_id_t id,struct qemu_plugin_tb *block) {
    (void)id;
    for(size_t i=0;i<qemu_plugin_tb_n_insns(block);++i) {
        struct qemu_plugin_insn *instruction=qemu_plugin_tb_get_insn(block,i);
        for(unsigned n=0;n<G_N_ELEMENTS(points);++n)if(qemu_plugin_insn_vaddr(instruction)==points[n])
            qemu_plugin_register_vcpu_insn_exec_cb(instruction,observe,QEMU_PLUGIN_CB_R_REGS,(void *)(uintptr_t)n);
    }
}
static void finish(qemu_plugin_id_t id,void *context) {
    (void)id;(void)context;
    for(unsigned n=0;n<G_N_ELEMENTS(points);++n)
        fprintf(output,"{\"kind\":\"total\",\"pc\":\"0x%"PRIx64"\",\"hits\":%"PRIu64",\"recorded\":%"PRIu64"}\n",
                points[n],counts[n],counts[n]<64?counts[n]:64);
    fputs("{\"kind\":\"end\"}\n",output);fclose(output);
}
QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,const qemu_info_t *info,int argc,char **argv) {
    if(!info->system_emulation || argc<1 || argc>2 || strncmp(argv[0],"out=",4))return -1;
    if(argc==2) {
        if(strncmp(argv[1],"record-offset=",14))return -1;
        char *end=NULL;record_offset=g_ascii_strtoull(argv[1]+14,&end,0);
        if(!record_offset || record_offset>1048576 || !end || *end)return -1;
    }
    output=fopen(argv[0]+4,"wx");if(!output)return -1;
    qemu_plugin_register_vcpu_init_cb(id,initialize);qemu_plugin_register_vcpu_tb_trans_cb(id,translate);
    qemu_plugin_register_atexit_cb(id,finish,0);return 0;
}
