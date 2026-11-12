import unittest

from host.z63_log_profile import profile, body_product, producer_tables
import struct


class Z63LogProfileTests(unittest.TestCase):
    def test_zr_base_and_native_body_policy(self):
        p = profile()
        self.assertEqual(p['m1_base_hex'], '3903ee00eaffe4ff5204dcff05001a00f303')
        self.assertEqual(p['body_policy'], 'preserve-original-producer-composition')
        self.assertFalse(p['physical_color_qualified'])
        identity = (16384, 0, 0, 0, 16384, 0, 0, 0, 16384)
        self.assertEqual(body_product(p['m1_base_q10'], identity), tuple(p['m1_base_q10']))
        body = (16000, 384, 0, 0, 16000, 384, 384, 0, 16000)
        got = body_product(p['m1_base_q10'], body)
        self.assertNotEqual(got, tuple(p['m1_base_q10']))
        self.assertEqual(got, (805, 252, -16, -28, 1079, -9, 29, 26, 988))

    def test_invalid_and_overflowing_body(self):
        base = profile()['m1_base_q10']
        for body in ((0,)*8, (float('nan'),)*9, (1.5,)*9, (32768,)*9):
            with self.assertRaises(ValueError):
                body_product(base, body)
        with self.assertRaises(ValueError):
            body_product((32767,)*9, (32767,)*9)

    def test_curve_and_compensation_contract(self):
        m1, m2, rgb, nlg, cpxs = producer_tables()
        self.assertEqual(tuple(map(len, (m1, m2, rgb, nlg, cpxs))), (18, 18, 1374, 458, 384))
        channels = struct.unpack('<687H', rgb)
        self.assertEqual(channels[:229], channels[229:458])
        self.assertEqual(channels[:229], channels[458:])
        self.assertEqual((channels[0], channels[228]), (2997, 24693))
        self.assertEqual(struct.unpack('<229H', nlg), tuple((x+4)//8 for x in channels[:229]))
        self.assertEqual(struct.unpack('<192h', cpxs), (253,-28,-19,252,26,50)*32)


if __name__ == '__main__':
    unittest.main()
