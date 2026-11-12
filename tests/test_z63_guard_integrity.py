"""Execute generated pre-core guards with corruption and hostile registers."""
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from host.z63_placement import guards, MARKER, INTEGRITY_CODE
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
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
            self.assertEqual(binary.read_bytes(),INTEGRITY_CODE+bytes(32))

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
