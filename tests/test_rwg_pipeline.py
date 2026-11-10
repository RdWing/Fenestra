import copy
import unittest
import numpy as np

from host import rwg_pipeline as p
from host.log3g10_reference import reference, matrix
from host.mipu_color_reference import matrix_product


class RwgPipelineTests(unittest.TestCase):
    def setUp(self):
        self.grid = reference()['grid']
        self.c = np.array(matrix(bytes.fromhex(reference()['matrix_hex']))).reshape(3, 3)
        self.body = np.array([[16243, 99, 42], [-87, 16534, -63], [-11, -7, 16402]])

    def profile(self, basis=None):
        return p.build_profile(self.c, np.eye(3) if basis is None else basis,
                               self.body, self.grid, linear_per_node=.00045, ceiling=32736)

    def test_basis_direction_and_body_composition(self):
        basis = np.array([[.9, .05, .02], [.03, 1.1, -.01], [.01, -.02, 1.05]])
        target = p.camera_to_rwg(self.c, basis)
        x = np.array([.08, .31, .72])
        np.testing.assert_allclose(p.rwg_to_xyz() @ target @ x, self.c @ basis @ x, atol=1e-14)
        self.assertGreater(np.max(np.abs(target - p.camera_to_rwg(self.c, basis.T))), .01)
        base, effective = p.calibrated_base(target, self.body)
        # The checked original helper sees the factor-two blended base and a
        # divisor of 32768; this catches applying body calibration twice.
        original = matrix_product((2 * base).flatten().tolist(), self.body.flatten().tolist(), 32768)
        np.testing.assert_array_equal(effective.flatten(), original)
        self.assertLess(np.max(np.abs(effective / 1024 - target)), .0015)
        with self.assertRaises(ValueError):
            p.camera_to_rwg(self.c, np.zeros((3, 3)))

    def test_basis_fit_independent_holdout_and_rank_rejection(self):
        rng = np.random.default_rng(201)
        source = rng.uniform(.1, 1, (120, 3))
        basis = np.array([[.92, .13, -.03], [.01, 1.02, -.01], [-.02, .06, .96]])
        fit, stats = p.fit_linear(source[:80], source[:80] @ basis.T)
        np.testing.assert_allclose(source[80:] @ fit.T, source[80:] @ basis.T, atol=1e-14)
        self.assertLess(max(stats['weighted_rms']), 1e-13)
        neutral = np.tile(np.linspace(.1, 1, 40)[:, None], (1, 3))
        for src, dst in ((neutral, neutral), (source, source * float('nan')),
                         (source, -np.ones_like(source)), (source[:, :2], source)):
            with self.assertRaises(ValueError):
                p.fit_linear(src, dst)

    def test_curve_pairs_nlg_plateau_and_neutral(self):
        profile = self.profile()
        rgb = np.array(profile['rgb15'])
        self.assertEqual(rgb.shape, (6, 229))
        for bank in rgb:
            np.testing.assert_array_equal(bank, rgb[0])
            self.assertTrue(np.all(np.diff(bank) >= 0))
        np.testing.assert_array_equal(profile['nlg12'], (rgb[0] + 4) // 8)
        # RED's 18% placement, independently of the grid's interpolation.
        self.assertAlmostEqual(float(p.log3g10(.18)), 1/3, places=6)
        self.assertGreater(rgb[0, -1], 24693)
        clipped, nlg = p.tables(self.grid, linear_per_node=.00045, ceiling=24693)
        self.assertEqual(clipped[0, -1], 24693)
        self.assertEqual(nlg[-1], 3087)
        self.assertFalse(profile['recording_qualified'])

    def test_downstream_compensation_and_noncommuting_order(self):
        np.testing.assert_array_equal(p.compensation(), [253, -28, -19, 252, 26, 50])
        profile = self.profile()
        values = np.array([[.01, .5, 1], [.3, .1, .6], [.18, .18, .18]])
        encoded = p.forward(profile, values)
        recovered = (encoded - [0, 512, 512]) @ p.invert(p.E_Q9 / 512).T / 1023
        target = p.log3g10(values @ (np.array(profile['m1_effective_q10']) / 1024).T)
        self.assertLess(np.max(np.abs(recovered - target)), .001)
        wrong_order = p.log3g10(values) @ (np.array(profile['m1_effective_q10']) / 1024).T
        self.assertGreater(np.max(np.abs(recovered - wrong_order)), .05)
        bad = copy.deepcopy(profile)
        bad['rgb15'][1][20] += 1
        with self.assertRaises(ValueError):
            p.forward(bad, values)
        bad = copy.deepcopy(profile)
        bad['cpxs_q8'][1][0] += 1
        with self.assertRaises(ValueError):
            p.forward(bad, values)

    def test_bounds_and_signed_rounding(self):
        np.testing.assert_array_equal(p.round_away(np.array([-.5, .5, -1.5, 1.5])), [-1, 1, -2, 2])
        for body in (np.zeros((3, 3)), self.body + .1, np.eye(3) * 32768):
            with self.assertRaises(ValueError):
                p.calibrated_base(np.eye(3), body)
        with self.assertRaises(ValueError):
            p.calibrated_base(np.eye(3) * 5, np.eye(3) * 16384)
        with self.assertRaises(ValueError):
            p.tables(self.grid, linear_per_node=float('nan'), ceiling=32736)
        with self.assertRaises(ValueError):
            p.tables(self.grid, linear_per_node=.00045, ceiling=32768)

    def test_inverse_recovers_input_and_refuses_clipping(self):
        profile = self.profile()
        x = np.random.default_rng(204).uniform(.1, .7, (40, 3))
        codes = p.forward(profile, x)
        args = dict(m1_q10=profile['m1_effective_q10'], m2_q9=profile['m2_q9'],
                    curve15=np.array(profile['rgb15'])[::2], grid=self.grid,
                    cpxs_ring_q8=profile['cpxs_q8'], origin_degrees=0.,
                    y2r_q10=profile['y2r_q10'], file_ycc_q9=profile['file_ycc_q9'])
        recovered = p.recover_pre_m1(codes, **args) * profile['linear_per_node']
        np.testing.assert_allclose(recovered, x, atol=1e-10, rtol=0)
        clipped = copy.deepcopy(profile)
        clipped['rgb15'] = p.tables(self.grid, linear_per_node=.00045, ceiling=24693)[0].tolist()
        args['curve15'] = np.array(clipped['rgb15'])[::2]
        with self.assertRaises(ValueError):
            p.recover_pre_m1(p.forward(clipped, [[100., 100., 100.]]), **args)
        with self.assertRaises(ValueError):
            p.cpxs_inverse([[0, 10, 20]], np.zeros((32, 6)), 0)

    def test_pixel_inverse_matches_scalar_and_preserves_linear_mean(self):
        profile = self.profile()
        args = dict(m1_q10=profile['m1_effective_q10'], m2_q9=profile['m2_q9'],
                    curve15=np.array(profile['rgb15'])[::2], grid=self.grid,
                    cpxs_ring_q8=profile['cpxs_q8'], origin_degrees=0.,
                    y2r_q10=profile['y2r_q10'], file_ycc_q9=profile['file_ycc_q9'])
        x = np.random.default_rng(20261105).uniform(.1, 1., (256, 3))
        codes = p.forward(profile, x)
        got, valid = p.recover_pre_m1_pixels(codes, **args)
        self.assertTrue(valid.all())
        np.testing.assert_allclose(got, p.recover_pre_m1(codes, **args), atol=1e-7)
        np.testing.assert_allclose(got.mean(axis=0) * profile['linear_per_node'],
                                   x.mean(axis=0), atol=1e-10)
        wrong = p.recover_pre_m1(codes.mean(axis=0)[None], **args)
        self.assertGreater(np.max(np.abs(wrong * profile['linear_per_node']
                                        - x.mean(axis=0))), .01)
        clipped = p.forward(profile, [[100., 100., 100.]])
        _, valid = p.recover_pre_m1_pixels(np.concatenate([codes, clipped]), **args)
        self.assertFalse(valid[-1])
        with self.assertRaises(ValueError):
            p.cpxs_inverse_pixels([[0, 10, 20]], np.zeros((32, 6)), 0)
        for inverse in (p.cpxs_inverse, p.cpxs_inverse_pixels):
            with self.assertRaises(ValueError):
                inverse([[30, 0, 0]], np.zeros((32, 6)), 0)

    def test_pixel_inverse_nonconstant_sector_mapping(self):
        ring = np.tile([256., 0, 0, 256, 0, 0], (32, 1))
        angle = np.arange(32) * np.pi / 16
        ring[:, 0] += 15 * np.sin(angle)
        ring[:, 3] += 10 * np.cos(angle)
        ring[:, 4] = 5 * np.sin(angle)
        x = np.random.default_rng(66).normal(size=(300, 3)) * 30
        encoded = p.cpxs_apply(x, ring, 179.646)
        np.testing.assert_allclose(p.cpxs_inverse_pixels(encoded, ring, 179.646),
                                   x, atol=1e-7)


if __name__ == '__main__':
    unittest.main()
