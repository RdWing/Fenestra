"""Execute generated pre-core guards with corruption and hostile registers."""
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from host.z63_placement import guards, MARKER, INTEGRITY_CODE, BOOTSTRAP_CODE
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
import unicorn.arm64_const as arm

ROOT=Path(__file__).resolve().parents[1]


class GuardIntegrityTests(unittest.TestCase):
    def test_validator_matches_assembled_source(self):
        clang,linker,objcopy=map(shutil.which,('clang','ld.lld','llvm-objcopy'))
        if not all((clang,linker,objcopy)):self.skipTest('LLVM target tools required')
        with tempfile.TemporaryDirectory() as tmp:
            obj,elf,binary=(Path(tmp)/n for n in ('guard.o','guard.elf','guard.bin'))
            subprocess.run([clang,'--target=aarch64-none-elf','-c',str(ROOT/'src/platform/z63_c201/guard_integrity.S'),'-o',str(obj)],check=True)
            subprocess.run([linker,'-m','aarch64elf','-Ttext=0','--entry=fx_guard_integrity',str(obj),'-o',str(elf)],check=True)
            subprocess.run([objcopy,'-O','binary',str(elf),str(binary)],check=True)
            self.assertEqual(binary.read_bytes(),INTEGRITY_CODE+bytes(72))
            subprocess.run([clang,'--target=aarch64-none-elf','-c',str(ROOT/'src/platform/z63_c201/guard_bootstrap.S'),'-o',str(obj)],check=True)
            subprocess.run([linker,'-m','aarch64elf','-Ttext=0','--entry=fx_boot_guard',str(obj),'-o',str(elf)],check=True)
            subprocess.run([objcopy,'-O','binary',str(elf),str(binary)],check=True)
            self.assertEqual(binary.read_bytes(),BOOTSTRAP_CODE)

    def test_stock_completion_precedes_optional_init_and_inactive_hooks_stay_stock(self):
        base,begin,end,g0=0x40000000,0x40001000,0x40001400,0x40002000
        site,normal,slot,state,message,stop=base+0x100,base+0x200,0x800080,0x801000,0x802000,0x80fff0
        profile={'image_base':base,'probe_code_region':{'begin':begin,'end':end},
                 'guard_region':{'begin':g0,'end':g0+0x1000},'sysctl':{'dispatcher':site},
                 'late_initialization':{'descriptor_slot':slot,'original_descriptor':0x800900,
                     'state_min':0x800000,'state_max':0x80ff00,'state_magic':0x465a634d}}
        original=bytearray(0x4000)
        stock=(0xa9bc67fe,0xa9015ff8,0xa90257f6,0xa9034ff4,0x52800540,0x528266e1,
               0xa9434ff4,0xa94257f6,0xa9415ff8,0xa8c467fe,0xd65f03c0)
        struct.pack_into('<11I',original,0x100,*stock)
        struct.pack_into('<I',original,0x200,0xa9bf7bfd)
        core=bytearray(1024);core[-8:]=MARKER
        for offset in (0,64,128):struct.pack_into('<I',core,offset,0xd65f03c0)
        blob,entries=guards(profile,original,{site:(begin,False),normal:(begin+64,False)},core,begin+128)
        cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);cpu.mem_map(base,0x4000);cpu.mem_write(base,bytes(original))
        cpu.mem_write(g0,blob);cpu.mem_map(0x800000,0x10000)
        trace=[]
        def observed(uc,pc,size,data):
            if pc==site+16:trace.append('stock')
            elif pc==begin+128:
                self.assertEqual(trace,['stock']);trace.append('optional')
                uc.reg_write(arm.UC_ARM64_REG_X0,0xbad) # Must not replace stock return.
            else:trace.append('normal-core')
        for pc in (site+16,begin,begin+128):cpu.hook_add(UC_HOOK_CODE,observed,begin=pc,end=pc)
        def run(pc,end_pc):
            for i in range(31):cpu.reg_write(getattr(arm,'UC_ARM64_REG_X'+str(i)),0x803000+i*16)
            cpu.reg_write(arm.UC_ARM64_REG_X0,message)
            cpu.reg_write(arm.UC_ARM64_REG_X1,0)
            cpu.reg_write(arm.UC_ARM64_REG_LR,stop)
            cpu.reg_write(arm.UC_ARM64_REG_SP,0x808000)
            cpu.reg_write(arm.UC_ARM64_REG_PSTATE,0xa00003c5)
            cpu.emu_start(pc,end_pc,count=10000)
            self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),end_pc)
            self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PSTATE)&0x3c0,0x3c0)
            return [cpu.reg_read(getattr(arm,'UC_ARM64_REG_X'+str(i))) for i in range(31)]+[
                cpu.reg_read(arm.UC_ARM64_REG_SP),cpu.reg_read(arm.UC_ARM64_REG_NZCV)]
        for event in (0,8,19,20,24,25):
            for present in (False,True):
                trace.clear();cpu.mem_write(begin,bytes(core) if present else bytes(1016)+MARKER)
                cpu.ctl_remove_cache(begin,end)
                cpu.mem_write(slot,struct.pack('<Q',0x800900));cpu.mem_write(message+32,struct.pack('<I',event))
                expected=run(site,stop);trace.clear()
                actual=run(entries[site],stop)
                if not present or event!=20:self.assertEqual(actual,expected)
                self.assertEqual(trace,['stock','optional'] if event==20 and present else ['stock'])
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_X0),42)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_SP),0x808000)
                self.assertEqual(struct.unpack('<Q',cpu.mem_read(slot,8))[0],0x800900)
        cpu.mem_write(begin,bytes(core));cpu.ctl_remove_cache(begin,end)
        for pointer,magic,allowed in ((0,0,False),(0x800900,0,False),(state+1,0,False),
                (0x7ffff8,0,False),(0x810000,0,False),(state,0,False),(state,0x465a634d,True)):
            cpu.mem_write(slot,struct.pack('<Q',pointer));cpu.mem_write(state+64,struct.pack('<I',magic))
            run(entries[normal],begin+64 if allowed else normal+4)
        # Negative control: the former argument reload corrupted stock x1.
        cpu.mem_write(slot,struct.pack('<Q',0x800900));cpu.mem_write(message+32,struct.pack('<I',20))
        cpu.mem_write(begin,bytes(1016)+MARKER);cpu.ctl_remove_cache(begin,end)
        reload_at=entries[site]+0x2c
        cpu.mem_write(reload_at,struct.pack('<I',0xa94007e0))
        cpu.ctl_remove_cache(reload_at,reload_at+4)
        expected=run(site,stop);trace.clear();former=run(entries[site],stop)
        self.assertNotEqual(former[1],expected[1])

    def test_corruption_falls_back_without_changing_machine_state(self):
        base,begin,end,g0=0x40000000,0x40001000,0x40001400,0x40002000
        profile={'image_base':base,'probe_code_region':{'begin':begin,'end':end},
                 'guard_region':{'begin':g0,'end':g0+0x1000},
                 'video_quality':{'hooks':[{'address':base+0x108,'tail':True}]}}
        original=bytearray(0x4000)
        # Entry, BL, and tail B: the same guard must keep each continuation.
        for offset,word in ((0x100,0xa9bf7bfd),(0x104,0x9400003f),(0x108,0x1400003e)):
            struct.pack_into('<I',original,offset,word)
        core=bytes((i*71+13)%256 for i in range(1016))+MARKER
        hooks={base+0x100:(begin,False),base+0x104:(begin+4,True),base+0x108:(begin+8,False)}
        blob,entries=guards(profile,original,hooks,core)
        cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);cpu.mem_map(base,0x4000);cpu.mem_write(base,bytes(original))
        cpu.mem_write(g0,blob);cpu.mem_map(0x800000,0x10000)
        regs=[getattr(arm,'UC_ARM64_REG_X'+str(i)) for i in range(31)]
        state_regs=regs+[arm.UC_ARM64_REG_SP,arm.UC_ARM64_REG_NZCV,arm.UC_ARM64_REG_PSTATE]
        initial=[0x801000+i*16 for i in range(31)]+[0x808000,0xa0000000,0xa00003c5]
        def execute(pc,stop):
            cpu.mem_write(0x808000-112,b'\xa5'*128)
            for reg,value in zip(state_regs,initial):cpu.reg_write(reg,value)
            cpu.emu_start(pc,stop,count=10000)
            self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),stop)
            self.assertEqual(bytes(cpu.mem_read(0x808000-112,16)),b'\xa5'*16)
            self.assertEqual(bytes(cpu.mem_read(0x808000,16)),b'\xa5'*16)
            return [cpu.reg_read(reg) for reg in state_regs]
        for site,(target,call) in hooks.items():
            continuation=base+0x200 if site!=base+0x100 else site+4
            stock_state=execute(site,continuation)
            # Guards entered after the patched BL see its link already set.
            prior_link=initial[30]
            if call:initial[30]=site+4
            for corrupt in (None,0,4,511,1015,1016,1023,'blank-marker-kept','erased'):
                changed=bytearray(core)
                if isinstance(corrupt,int):changed[corrupt]^=1
                elif corrupt=='blank-marker-kept':changed[:-8]=bytes(len(changed)-8)
                elif corrupt=='erased':changed[:]=b'\xff'*len(changed)
                cpu.mem_write(begin,bytes(changed))
                got=execute(entries[site],target if corrupt is None else continuation)
                self.assertEqual(got,initial if corrupt is None else stock_state)
            initial[30]=prior_link
