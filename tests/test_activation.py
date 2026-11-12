"""Failure injection at installation/retirement and original register boundaries."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from z63_activation import enable_record
from z63_placement import UPDATE_CODE,_branch


class ActivationTests(unittest.TestCase):
    def test_transaction_failures_and_retained_ownership(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'activation'
            subprocess.run(['cc','-std=c11','-Wall','-Wextra','-I',str(ROOT/'include'),
                str(ROOT/'tests/activation_fixture.c'),str(ROOT/'src/activation.c'),str(ROOT/'src/memory.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

    def test_exact_build_record_rejects_damage_and_extra_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'activation.dylib'
            subprocess.run(['cc','-std=c11','-shared','-fPIC','-I',str(ROOT/'include'),
                            str(ROOT/'src/activation.c'),str(ROOT/'src/memory.c'),'-o',str(binary)],check=True)
            lib=ctypes.CDLL(str(binary));verify=lib.fx_activation_record
            verify.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]
            identity=bytes(range(32));record=enable_record(identity)
            self.assertEqual(verify(record,64,identity),0)
            for i in range(64):
                changed=bytearray(record);changed[i]^=1
                self.assertNotEqual(verify(bytes(changed),64,identity),0,i)
            for length in (0,1,32,63,65):self.assertNotEqual(verify(record+b'x',length,identity),0)
            self.assertNotEqual(verify(record,64,bytes(32)),0)

    def test_updater_guard_matches_source(self):
        compiler,linker,objcopy=map(shutil.which,('clang','ld.lld','llvm-objcopy'))
        if not all((compiler,linker,objcopy)):self.skipTest('LLVM tools required')
        with tempfile.TemporaryDirectory() as tmp:
            obj,elf,binary=(Path(tmp)/n for n in ('guard.o','guard.elf','guard.bin'))
            subprocess.run([compiler,'--target=aarch64-none-elf','-c',str(ROOT/'src/platform/z63_c201/guard_update.S'),'-o',str(obj)],check=True)
            subprocess.run([linker,'-m','aarch64elf','-Ttext=0','--entry=fx_update_guard_one',str(obj),'-o',str(elf)],check=True)
            subprocess.run([objcopy,'-O','binary',str(elf),str(binary)],check=True)
            self.assertEqual(binary.read_bytes(),UPDATE_CODE)

    def test_updater_guard_is_independent_and_retains_admission(self):
        from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
        import unicorn.arm64_const as arm
        base,ram,stop=0x40000000,0x800000,0x800ff0
        cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);cpu.mem_map(base,4096);cpu.mem_map(ram,65536)
        code=bytearray(UPDATE_CODE)
        for offset,target in ((0x18,base+0x800),(0x34,base+0x900)):
            struct.pack_into('<I',code,offset,_branch(base+offset,target))
        struct.pack_into('<Q',code,len(UPDATE_CODE)-8,ram)
        cpu.mem_write(base,bytes(code))
        for entry,target in ((base,base+0x800),(base+0x1c,base+0x900)):
            for state in (0,1,2,3,0xffffffff):
                cpu.mem_write(ram,struct.pack('<I',state))
                initial=[0x802000+i*16 for i in range(31)];initial[30]=stop
                for i,value in enumerate(initial):cpu.reg_write(getattr(arm,'UC_ARM64_REG_X'+str(i)),value)
                cpu.reg_write(arm.UC_ARM64_REG_SP,0x808000);cpu.reg_write(arm.UC_ARM64_REG_NZCV,0xa0000000)
                allowed=state in (0,2)
                cpu.emu_start(entry,target if allowed else stop,count=1000)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),target if allowed else stop)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_SP),0x808000)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_NZCV),0xa0000000)
                for i,value in enumerate(initial):
                    self.assertEqual(cpu.reg_read(getattr(arm,'UC_ARM64_REG_X'+str(i))),2 if i==0 and not allowed else value)
                self.assertEqual(struct.unpack('<I',cpu.mem_read(ram,4))[0],2 if allowed else state)

    def test_feature_gate_distinguishes_install_drain_and_update(self):
        from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
        import unicorn.arm64_const as arm
        from z63_activation import profile_for,UPDATE_SITES,CONTROL_RAM
        from z63_placement import guards,MARKER
        base,begin,end,g0,g1=0x40160000,0x401a0000,0x401a0400,0x40194180,0x40195000
        dispatcher,feature,shell,slot,state=0x40d66ef0,0x40250000,0x403edb18,0x800000,0x801000
        profile=profile_for(dict(image_base=base,probe_code_region=dict(begin=begin,end=end),
            guard_region=dict(begin=g0,end=g1),sysctl=dict(dispatcher=dispatcher),
            late_initialization=dict(descriptor_slot=slot,original_descriptor=0x802000,
                state_min=0x800000,state_max=0x80f000,state_magic=0x465a634d)),True)
        original=bytearray(0x1000000)
        struct.pack_into('<4I',original,dispatcher-base,0xa9bc67fe,0xa9015ff8,0xa90257f6,0xa9034ff4)
        struct.pack_into('<I',original,feature-base,0xa9bf7bfd)
        struct.pack_into('<I',original,shell-base,0xa9bf7bfd)
        for site,target in UPDATE_SITES:struct.pack_into('<I',original,site-base,_branch(site,target))
        core=bytes(1016)+MARKER
        blob,entries=guards(profile,original,{dispatcher:(begin,False),feature:(begin+4,False),shell:(begin+12,False)},core,begin+8,bytes(range(32)))
        cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM);cpu.mem_map(base,len(original));cpu.mem_write(base,bytes(original))
        cpu.mem_write(begin,core);cpu.mem_write(g0,blob);cpu.mem_map(0x800000,0x10000)
        cpu.mem_map(CONTROL_RAM&~4095,4096);cpu.mem_write(slot,struct.pack('<Q',state))
        cpu.mem_write(state+64,struct.pack('<I',0x465a634d))
        for session in (0,1,2):
            for active in (0,1,2,3,5,0xffffffff):
                cpu.mem_write(CONTROL_RAM,struct.pack('<I',session));cpu.mem_write(state+76,struct.pack('<I',active))
                cpu.reg_write(arm.UC_ARM64_REG_SP,0x808000)
                stop=begin+4 if session!=2 and active in (1,3) else feature+4
                cpu.emu_start(entries[feature],stop,count=100000)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),stop,(session,active))
                cpu.reg_write(arm.UC_ARM64_REG_SP,0x808000)
                cpu.emu_start(entries[shell],begin+12,count=100000)
                self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),begin+12,'published shell was abandoned')
