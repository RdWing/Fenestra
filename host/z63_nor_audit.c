/* Read-only QEMU observation. No firmware patch or device access. Log every
 * CPU store to modeled NOR/controller and status reads in the original RAM
 * controller helpers; no sampling or event-count truncation. */
#include <qemu-plugin.h>
#include <glib.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
QEMU_PLUGIN_EXPORT int qemu_plugin_version=QEMU_PLUGIN_VERSION;
static FILE *output;
static GMutex mutex;
static uint64_t sequence;
static bool main_cpu[16];
static void initialize_cpu(qemu_plugin_id_t id,unsigned cpu) {
    (void)id;if(cpu>=16)return;
    g_autoptr(GArray) registers=qemu_plugin_get_registers();
    for(guint i=0;i<registers->len;++i) {
        qemu_plugin_reg_descriptor *r=&g_array_index(registers,qemu_plugin_reg_descriptor,i);
        if(!strcmp(r->name,"x0"))main_cpu[cpu]=true;
    }
}
static void access_memory(unsigned cpu,qemu_plugin_meminfo_t info,uint64_t va,void *context) {
    /* The M4 has a separate physical address space: its 0x400xxxxx APB
     * registers are not MAIN's NOR window. Identify AArch64 by its registers. */
    if(cpu>=16 || !main_cpu[cpu])return;
    struct qemu_plugin_hwaddr *address=qemu_plugin_get_hwaddr(info,va);
    if(!address)return;
    uint64_t pa=qemu_plugin_hwaddr_phys_addr(address);
    int store=qemu_plugin_mem_is_store(info);
    if(!(pa>=0x0e007000 && pa<0x0e007100) &&
       !(store && pa>=0x40000000 && pa<0x48000000))return;
    qemu_plugin_mem_value value=qemu_plugin_mem_get_value(info);
    uint64_t bits=0;int supported=1;
    switch(value.type) {
    case QEMU_PLUGIN_MEM_VALUE_U8:bits=value.data.u8;break;
    case QEMU_PLUGIN_MEM_VALUE_U16:bits=value.data.u16;break;
    case QEMU_PLUGIN_MEM_VALUE_U32:bits=value.data.u32;break;
    case QEMU_PLUGIN_MEM_VALUE_U64:bits=value.data.u64;break;
    default:supported=0;break;
    }
    g_mutex_lock(&mutex);
    fprintf(output,"%" PRIu64 " %u %c %" PRIx64 " %" PRIx64 " %u %" PRIx64 " %d\n",
        sequence++,cpu,store?'W':'R',(uint64_t)(uintptr_t)context,pa,
        1u<<qemu_plugin_mem_size_shift(info),bits,supported);
    fflush(output);
    g_mutex_unlock(&mutex);
}
static void translate(qemu_plugin_id_t id,struct qemu_plugin_tb *block) {
    (void)id;
    for(size_t i=0;i<qemu_plugin_tb_n_insns(block);++i) {
        struct qemu_plugin_insn *instruction=qemu_plugin_tb_get_insn(block,i);
        uint64_t pc=qemu_plugin_insn_vaddr(instruction);
        qemu_plugin_register_vcpu_mem_cb(instruction,access_memory,QEMU_PLUGIN_CB_NO_REGS,
            pc>=UINT64_C(0xa02bde000) && pc<UINT64_C(0xa02be1000)?QEMU_PLUGIN_MEM_RW:QEMU_PLUGIN_MEM_W,
            (void *)(uintptr_t)pc);
    }
}
static void finish(qemu_plugin_id_t id,void *context) {
    (void)id;(void)context;
    fprintf(output,"END %" PRIu64 "\n",sequence);fclose(output);
}
QEMU_PLUGIN_EXPORT int qemu_plugin_install(qemu_plugin_id_t id,const qemu_info_t *info,int argc,char **argv) {
    if(!info->system_emulation || argc!=1 || strncmp(argv[0],"out=",4))return -1;
    output=fopen(argv[0]+4,"wx");if(!output)return -1;
    fputs("FXNOR1 MAIN AArch64 CPU stores; original RAM helper status reads; separate M4 address space excluded; no DMA or physical busy-fetch model\n",output);
    qemu_plugin_register_vcpu_init_cb(id,initialize_cpu);
    qemu_plugin_register_vcpu_tb_trans_cb(id,translate);
    qemu_plugin_register_atexit_cb(id,finish,0);return 0;
}
