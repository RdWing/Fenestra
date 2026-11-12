from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from elf_symbols import local_function


class ElfSymbolsTests(unittest.TestCase):
    def test_duplicate_local_names_are_resolved_by_compilation_unit(self):
        cc,linker=shutil.which('clang'),shutil.which('ld.lld')
        if not cc or not linker:self.skipTest('ELF target tools required')
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);objects=[]
            for i,unit in enumerate(('first','second')):
                source=p/(unit+'.c');obj=p/(unit+'.o');objects.append(str(obj))
                source.write_text('__attribute__((noinline,used)) static int activate(void){return '+str(i+10)+';}\nint '+unit+'(void){return activate();}\n')
                subprocess.run([cc,'--target=aarch64-none-elf','-c',str(source),'-o',str(obj)],check=True)
            elf=p/'test.elf'
            subprocess.run([linker,'-m','aarch64elf','-Ttext=0x401a0000','--entry=first',*objects,'-o',str(elf)],check=True)
            first=local_function(elf,'first.c','activate');second=local_function(elf,'second.c','activate')
            self.assertNotEqual(first[0],second[0]);self.assertNotEqual(first[1],second[1])
            with self.assertRaises(ValueError):local_function(elf,'missing.c','activate')
