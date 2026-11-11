import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def crc(data):
    value=0
    for byte in data:
        value^=byte
        for bit in range(8):
            value=((value*2)^(7 if value>=128 else 0))%256
    return value


def word(payload,low=1):
    return low|(payload<<8)|(crc(payload.to_bytes(2,'little'))<<24)


class VideoSettingsTests(unittest.TestCase):
    def test_shared_records_migration_and_preservation(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as temporary:
            windows=sys.platform=='win32'
            library=Path(temporary)/('settings.dll' if windows else 'settings.so')
            sources=[str(ROOT/'src/video_settings.c')]
            if windows:
                # Explicit exports work with the Windows clang/MSVC linker;
                # ELF-style visibility and -fPIC are not a Windows contract.
                wrapper=Path(temporary)/'exports.c'
                wrapper.write_text('#include "fenestra_video_settings.h"\n'
                    '__declspec(dllexport) int test_read(uint32_t w,uint32_t *t){return fx_h265_settings_read(w,t); }\n'
                    '__declspec(dllexport) int test_write(uint32_t w,uint32_t t,uint32_t *o){return fx_h265_settings_write(w,t,o); }\n')
                sources.append(str(wrapper))
            subprocess.run([cc,'-std=c11','-shared',*([] if windows else ['-fPIC']),'-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'include'),*sources,'-o',str(library)],check=True)
            api=ctypes.CDLL(str(library))
            try:
                read=getattr(api,'test_read' if windows else 'fx_h265_settings_read')
                write=getattr(api,'test_write' if windows else 'fx_h265_settings_write')
                read.argtypes=[ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
                write.argtypes=[ctypes.c_uint32,ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32)]
                cases=0
                for version in (0xa000,0xc000):
                    for prores in range(4):
                        for h265 in range(5):
                            for log in range(3):
                                payload=version|prores|(h265<<2)|(7<<5)|(log<<8)|(3<<10)|(1<<12)
                                prior=word(payload)
                                observed=ctypes.c_uint32(99)
                                self.assertEqual(read(prior,ctypes.byref(observed)),1)
                                self.assertEqual(observed.value,h265)
                                for tier in range(5):
                                    encoded=ctypes.c_uint32(0xdeadbeef)
                                    self.assertEqual(write(prior,tier,ctypes.byref(encoded)),1)
                                    self.assertEqual(encoded.value,word((payload&~28)|(tier<<2)))
                                    cases+=1
                self.assertEqual(cases,600)
                for quality in range(4):
                    legacy=1|(0x63<<8)|(quality<<16)|(crc(bytes((0x63,quality)))<<24)
                    encoded=ctypes.c_uint32()
                    self.assertEqual(write(legacy,3,ctypes.byref(encoded)),1)
                    self.assertEqual(encoded.value,word(0xa000|quality|(3<<2)))
                for prior in (0,1):
                    encoded=ctypes.c_uint32()
                    self.assertEqual(write(prior,4,ctypes.byref(encoded)),1)
                    self.assertEqual(encoded.value,word(0xa010,prior))
                for prior in (0x12345601,word(0xa000)^0x1000000,word(0xa000|(5<<2)),word(0xa000|(3<<8)),word(0xa000,2)):
                    encoded=ctypes.c_uint32(0xdeadbeef)
                    self.assertEqual(write(prior,2,ctypes.byref(encoded)),0)
                    self.assertEqual(encoded.value,0xdeadbeef)
                encoded=ctypes.c_uint32(0xdeadbeef)
                self.assertEqual(write(1,5,ctypes.byref(encoded)),0)
                self.assertEqual(encoded.value,0xdeadbeef)
            finally:
                if windows:
                    import _ctypes
                    _ctypes.FreeLibrary(api._handle)
