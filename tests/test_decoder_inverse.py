import unittest
import numpy as np
from host.decoder_inverse import inverse_pixels


class DecoderInverseTests(unittest.TestCase):
    def test_positive_branch_roundtrip_with_signed_input(self):
        rng = np.random.default_rng(2011105)
        rows = rng.uniform(-.08, .8, (3000, 3))
        # Independently evaluate the published forward equation. The red and
        # green branches share t=.05, while blue dominance selects t=.5.
        encoded = []
        for rgb in rows:
            peak = max(rgb)
            if peak <= 0:
                encoded.append(rgb)
                continue
            t = .5 if rgb[2] > max(rgb[:2]) else .05
            m = min(rgb) / peak
            if m >= t:
                encoded.append(rgb)
            else:
                n = t * (max(0., (m + 1) / (t + 1))) ** ((t + 1) / t)
                encoded.append(peak + (rgb - peak) * (1 - n) / (1 - m))
        recovered, valid = inverse_pixels(encoded)
        self.assertGreater(valid.sum(), 2000)
        np.testing.assert_allclose(recovered[valid], rows[valid], atol=1e-13)
        self.assertTrue(np.any(recovered[valid] < 0))
        self.assertTrue(np.isnan(recovered[~valid]).all())

    def test_dark_clipped_branch_tie_and_neutral(self):
        rgb = [[.001]*3, [0., .1, .3], [.3, .01, .3], [.18]*3]
        recovered, valid = inverse_pixels(rgb)
        np.testing.assert_array_equal(valid, [False, False, False, True])
        np.testing.assert_array_equal(recovered[-1], rgb[-1])
        for args in ({'minimum_peak': 0}, {'maximum_derivative': .9},
                     {'branch_margin': 1}, {'minimum_peak': float('nan')}):
            with self.assertRaises(ValueError):
                inverse_pixels(rgb, **args)
        with np.errstate(all='raise'):
            rejected, mask = inverse_pixels([[-10., -20., -30.], [0., 0., 0.]])
        self.assertFalse(mask.any())
        self.assertTrue(np.isnan(rejected).all())

    def test_nonlinear_inverse_must_precede_average(self):
        rows = np.array([[.1, .2, .6], [.4, .3, .5]])
        inv, valid = inverse_pixels(rows)
        mean_inv, mean_valid = inverse_pixels(rows.mean(axis=0)[None])
        self.assertTrue(valid.all() and mean_valid.all())
        self.assertGreater(np.max(np.abs(inv.mean(axis=0) - mean_inv[0])), .001)


if __name__ == '__main__':
    unittest.main()
