import struct
import unittest
from host.mipu_color_reference import matrix_product, m1_registers


class MipuColorReferenceTest(unittest.TestCase):
    def test_composition_order(self):
        mix = [512,512,0,0,1024,0,0,0,1024]
        scale = [2048,0,0,0,1024,0,0,0,512]
        self.assertEqual(matrix_product(mix,scale,1024),[1024,512,0,0,1024,0,0,0,512])
        self.assertNotEqual(matrix_product(mix,scale,1024),matrix_product(scale,mix,1024))

    def test_signed_ties(self):
        a = [1,-1,0,0,1,0,0,0,1]
        self.assertEqual(matrix_product(a,[1,0,0,0,1,0,0,0,1],2),a)
        self.assertEqual(matrix_product(a,a,0),[0]*9)

    def test_narrowing(self):
        a = [32767]*9
        self.assertEqual(matrix_product(a,a,1),[3]*9)

    def test_driver_masks_without_saturation(self):
        block=struct.pack('<10H',65535,8192,65535,4096,32768,0,1,8191,8193,65535)
        self.assertEqual(m1_registers(block),[65535,8191<<16,4096,1<<16,8191|(1<<16),8191])

    def test_bounds(self):
        for block in (bytes(19),bytes(21)):
            with self.assertRaises(ValueError):m1_registers(block)
        with self.assertRaises(ValueError):matrix_product([32768]*9,[0]*9,1024)
        with self.assertRaises(ValueError):matrix_product([0]*9,[0]*9,-1)
