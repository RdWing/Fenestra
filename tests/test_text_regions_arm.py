"""Exercise the freestanding interrupt-mask facade, not its hosted branch."""
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
import unicorn.arm64_const as arm

ROOT=Path(__file__).resolve().parents[1]


class TextRegionsArmTests(unittest.TestCase):
    def test_busy_returns_with_original_mask_and_unpublished_node(self):
        clang,linker=shutil.which('clang'),shutil.which('ld.lld')
        if not clang or not linker:
            self.skipTest('AArch64 clang and ld.lld required')
        with tempfile.TemporaryDirectory() as tmp:
            obj,elf=Path(tmp)/'regions.o',Path(tmp)/'regions.elf'
            subprocess.run([clang,'--target=aarch64-none-elf','-O2','-ffreestanding',
                '-fno-builtin','-mno-outline-atomics','-mgeneral-regs-only',
                '-DFX_FREESTANDING=1','-I',str(ROOT/'include'),'-c',
                str(ROOT/'src/text_regions.c'),'-o',str(obj)],check=True)
            subprocess.run([linker,'-m','aarch64elf','-Ttext=0x46000000',
                '--entry=fx_native_text_regions_add',str(obj),'-o',str(elf)],check=True)
            data=elf.read_bytes();cpu=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
            ph=struct.unpack_from('<Q',data,32)[0];stride,count=struct.unpack_from('<HH',data,54)
            pages=set()
            for i in range(count):
                kind,flags,offset,address,_,size,extent,alignment=struct.unpack_from('<II6Q',data,ph+i*stride)
                if kind!=1:continue
                for page in range(address&~4095,(address+extent+4095)&~4095,4096):
                    if page not in pages:cpu.mem_map(page,4096);pages.add(page)
                if size:cpu.mem_write(address,data[offset:offset+size])
            entry=struct.unpack_from('<Q',data,24)[0]
            cpu.mem_map(0x100000,0x10000)
            for mask in (0,0x80,0x40,0x3c0):
                for busy in (1,0):
                    cpu.mem_write(0x100000,bytes(0x3000))
                    cpu.mem_write(0x100008,struct.pack('<I',busy))
                    for i,value in enumerate((0x100000,0x101000,0x102000,64)):
                        cpu.reg_write(arm.UC_ARM64_REG_X0+i,value)
                    cpu.reg_write(arm.UC_ARM64_REG_SP,0x10f000)
                    cpu.reg_write(arm.UC_ARM64_REG_LR,0x10fff0)
                    cpu.reg_write(arm.UC_ARM64_REG_PSTATE,5|mask)
                    cpu.emu_start(entry,0x10fff0,count=2000)
                    self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PC),0x10fff0)
                    self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_PSTATE)&0x3c0,mask)
                    if busy:
                        self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_X0),5) # FX_BUSY
                        self.assertEqual(bytes(cpu.mem_read(0x101000,56)),bytes(56))
                        self.assertEqual(bytes(cpu.mem_read(0x100000,16)),struct.pack('<QII',0,1,0))
                    else:
                        self.assertEqual(cpu.reg_read(arm.UC_ARM64_REG_X0),0)
                        self.assertEqual(struct.unpack('<Q',cpu.mem_read(0x101030,8))[0],0x100000)


if __name__=='__main__':unittest.main()
