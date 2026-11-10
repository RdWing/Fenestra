import math
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from log3g10_reference import reference, curve, matrix, verify


class ReferenceTests(unittest.TestCase):
    def test_original_execution_vectors(self):
        self.assertEqual(verify()['curve_samples'],687)
        self.assertFalse(verify()['camera_qualified'])

    def test_monotonic_and_saturation(self):
        d=reference()
        for ratio in (-32,-1,0,1,32):
            values=curve(d['grid'],ratio,d['constants'])
            self.assertEqual(values,sorted(values))
            self.assertTrue(all(0<=v<=32767 for v in values))
        self.assertEqual(curve([65535],32,d['constants']),[32767])

    def test_invalid_inputs(self):
        d=reference()
        for ratio in (math.nan,math.inf,33):
            with self.assertRaises(ValueError):curve([0],ratio,d['constants'])
        for grid in ([-1],[65536],[0.5]):
            with self.assertRaises(ValueError):curve(grid,0,d['constants'])
        for blob in (b'',bytes(36),b'\x01'+bytes(36),b'\0'+struct.pack('>9f',math.nan,*([0]*8))):
            with self.assertRaises(ValueError):matrix(blob)

    def test_matrix_preserves_signed_coefficients(self):
        d=reference();b=bytes.fromhex(d['matrix_hex'])
        m=matrix(b)
        self.assertEqual(b,b'\0'+struct.pack('>9f',*m))
        self.assertTrue(any(x<0 for x in m))

    def test_native_capability_refusal(self):
        import subprocess
        import tempfile
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            binary=str(Path(tmp)/'color')
            subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',
                '-I',str(root/'include'),str(root/'tests/video_color_fixture.c'),
                str(root/'src/platform/z63_c201/video_color.c'),str(root/'src/memory.c'),'-o',binary],check=True)
            subprocess.run([binary],check=True)
