import ctypes
from pathlib import Path
import subprocess
import tempfile
import unittest
import struct

ROOT=Path(__file__).resolve().parents[1]
from host.color_transplant import library,PARAMETERS,SAMPLES,SIZE,OFFSETS

class ColorTransplantTests(unittest.TestCase):
    def test_complete_rwg_configuration_and_failure_atomicity(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib,_=library(tmp)
            fn=lib.fx_z63_color_rwg_candidate
            fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,
                         ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,
                         ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t]
            fn.restype=ctypes.c_int
            p=(ctypes.c_ubyte*PARAMETERS)(*([0x5a]*PARAMETERS))
            p[0x1e8]=p[0x1e9]=0;p[0x263]=p[0x264]=2
            s=(ctypes.c_ubyte*SAMPLES)(*([0x69]*SAMPLES))
            out=(ctypes.c_ubyte*SIZE)(*([0xa5]*SIZE))
            m1=(ctypes.c_int16*9)(900,200,-76,-20,1060,-16,10,40,974)
            curve=(ctypes.c_uint16*229)(*[i*140 for i in range(229)])
            args=[out,p,PARAMETERS,s,SAMPLES,m1,9,curve,229]
            for index,value in ((0,None),(1,None),(2,PARAMETERS-1),(3,None),
                                (4,SAMPLES-1),(5,None),(6,8),(7,None),(8,228),
                                (5,ctypes.addressof(out)),(7,ctypes.addressof(out)),
                                (1,ctypes.addressof(out)),(3,ctypes.addressof(out))):
                bad=args.copy();bad[index]=value
                self.assertEqual(fn(*bad),0)
                self.assertEqual(bytes(out),b'\xa5'*SIZE)
            for value in (-4097,4096):
                m1[0]=value;self.assertEqual(fn(*args),0)
                self.assertEqual(bytes(out),b'\xa5'*SIZE)
            m1[0]=900
            curve[-1]=32764
            self.assertEqual(fn(*args),0)
            self.assertEqual(bytes(out),b'\xa5'*SIZE)
            curve[-1]=32763
            stock=bytes(p)+bytes(s)
            self.assertEqual(fn(*args),1)
            got=bytes(out)
            self.assertEqual(struct.unpack_from('<9h',got,0x1ea),tuple(m1))
            self.assertEqual(struct.unpack_from('<9h',got,0x248),
                             (109,366,37,-59,-197,256,256,-233,-23))
            for field,value in enumerate((253,-28,-19,252,26,50)):
                for bank in range(2):
                    self.assertEqual(struct.unpack_from('<32h',got,PARAMETERS+64*(2*field+bank)),
                                     (value,)*32)
            for offset in OFFSETS:
                self.assertEqual(struct.unpack_from('<229H',got,PARAMETERS+offset),tuple(curve))
            self.assertEqual(struct.unpack_from('<229H',got,PARAMETERS+0x16a2),
                             tuple((v+4)//8 for v in curve))
            allowed=set(range(0x1ea,0x1fc))|set(range(0x248,0x25a))
            allowed.update(range(PARAMETERS,PARAMETERS+768))
            for offset in (*OFFSETS,0x16a2):
                allowed.update(range(PARAMETERS+offset,PARAMETERS+offset+458))
            self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(stock,got)) if i not in allowed))
            self.assertEqual(bytes(p)+bytes(s),stock)

    def test_bounds_failure_atomicity_and_unchanged_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib,fn=library(tmp)
            p=(ctypes.c_ubyte*PARAMETERS)(*([0x5a]*PARAMETERS));p[0x263]=p[0x264]=2
            s=(ctypes.c_ubyte*SAMPLES)(*([0x69]*SAMPLES))
            out=(ctypes.c_ubyte*SIZE)(*([0xa5]*SIZE))
            curve=(ctypes.c_uint16*229)(*[i*100 for i in range(229)])
            args=[out,p,PARAMETERS,s,SAMPLES,curve,229,1024]
            for index,value in ((0,None),(1,None),(2,PARAMETERS-1),(2,PARAMETERS+1),
                                (3,None),(4,SAMPLES-1),(5,None),(6,228),(6,230),
                                (0,ctypes.addressof(p)),(1,ctypes.addressof(out)+1),
                                (3,ctypes.addressof(out)+SIZE-1),(5,ctypes.addressof(out))):
                bad=list(args);bad[index]=value
                self.assertEqual(fn(*bad),0)
                self.assertEqual(bytes(out),b'\xa5'*SIZE)
            for control in (0x263,0x264):
                p[control]=1;self.assertEqual(fn(*args),0);p[control]=2
                self.assertEqual(bytes(out),b'\xa5'*SIZE)
            for value in (65535,0):
                curve[20]=value;self.assertEqual(fn(*args),0)
                self.assertEqual(bytes(out),b'\xa5'*SIZE)
            curve[20]=2000
            before=bytes(p)+bytes(s)
            self.assertEqual(fn(*args),1)
            changed=set(range(0x248,0x25a))|{0x263,0x264}
            for offset in OFFSETS:changed.update(range(PARAMETERS+offset,PARAMETERS+offset+458))
            self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(before,bytes(out))) if i not in changed))
            self.assertEqual(bytes(p)+bytes(s),before)
            self.assertEqual(bytes(out)[PARAMETERS+0x16a2:PARAMETERS+0x186c],b'\x69'*458)


if __name__=='__main__':unittest.main()
