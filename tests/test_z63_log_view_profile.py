import unittest
from host.z63_log_view_profile import C6, matrices, matrix_record


class Z63LogViewProfileTests(unittest.TestCase):
    def test_distinct_panel_records(self):
        rear, evf = matrices(C6)
        self.assertEqual(rear.hex(), '0101ee0766fcacff4aff0006b6fe98ffdcfd8c0601000000')
        self.assertEqual(evf.hex(), '01017705ecfe9dffa8ff9f05b9feb4ff65fee80501000000')
        self.assertNotEqual(rear, evf)
        self.assertNotEqual(rear.hex(), '010165061afe81ff93ffaf05befeb7ff6cfedd0501000000')

    def test_reject_unrepresentable_or_wrong_target(self):
        for first in (-2049, 2048, 2116, 1.5):
            with self.assertRaises(ValueError):
                matrix_record((first,)+(0,)*8)
        with self.assertRaises(ValueError):
            matrices((1024,0,0,0,1024,0,0,0,1024))


if __name__ == '__main__':
    unittest.main()
