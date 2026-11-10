"""Offline Log3G10/RWG calibration and complete color-chain candidate.

The reconstruction method follows NikonFirmwarePatch's published Z8 colour
report at a21fc8c04b6dd863439c4192d387b755633287f6. No Z8 body calibration or
hook code is used. NumPy is an offline analysis dependency. These functions
neither install hooks nor certify that C2.01 executes the modelled pixel order.
"""
import math
import numpy as np

E_Q9 = np.array([[109, 366, 37], [-59, -197, 256], [256, -233, -23]])
Y2R_Q10 = np.array([[1024, 0, 1436], [1024, -352, -731], [1024, 1815, 0]])
RWG_XY = ((.780308, .304253), (.121595, 1.493994), (.095612, -.084589))


def array(value, shape, name):
    value = np.asarray(value, dtype=float)
    if value.shape != shape or not np.isfinite(value).all():
        raise ValueError(name + ': invalid shape or nonfinite values')
    return value


def invert(matrix):
    matrix = array(matrix, (3, 3), 'matrix')
    if np.linalg.cond(matrix) > 1e8:
        raise ValueError('matrix is singular or ill-conditioned')
    return np.linalg.inv(matrix)


def round_away(values):
    return np.sign(values) * np.floor(np.abs(values) + .5)


def rwg_to_xyz():
    p = np.array(RWG_XY)
    columns = np.array([p[:, 0] / p[:, 1], np.ones(3),
                        (1 - p.sum(axis=1)) / p[:, 1]])
    white = np.array([.3127 / .329, 1, (1 - .3127 - .329) / .329])
    return columns * (invert(columns) @ white)


def camera_to_rwg(camera_to_xyz, raw_from_m1):
    """P maps *pre-M1* linear RGB to the RAW matrix's input coordinates.

    P is mandatory: silently assuming identity confuses body calibration,
    white-balance normalization and the input basis. No exposure offset or
    RED decoder saturation mapping is included in this linear transform.
    """
    c = array(camera_to_xyz, (3, 3), 'camera-to-XYZ')
    p = array(raw_from_m1, (3, 3), 'RAW-from-M1 basis')
    invert(c)
    invert(p)
    return invert(rwg_to_xyz()) @ c @ p


def fit_linear(source, target):
    """Fit target = M * source, weighting each channel by target + 0.01.

    Inputs must already be linear and share exposure/WB normalization.
    Clipped samples and a decoder's nonlinear F mapping must be removed by
    the caller. Negative targets at or below -0.01 cannot use this weighting.
    A neutral ramp alone cannot determine a three-channel input basis.
    """
    x = np.asarray(source, dtype=float)
    if x.ndim != 2 or x.shape[1] != 3 or len(x) < 3 or not np.isfinite(x).all():
        raise ValueError('source must contain at least three finite RGB rows')
    y = array(target, x.shape, 'target')
    if np.any(y <= -.01):
        raise ValueError('target outside the positive residual-weight domain')
    rows = []
    conditions = []
    for channel in range(3):
        denominator = y[:, channel] + .01
        design = x / denominator[:, None]
        condition = np.linalg.cond(design)
        if condition > 1e6:
            raise ValueError('samples do not constrain an independent RGB basis')
        row, _, rank, _ = np.linalg.lstsq(design, y[:, channel] / denominator, rcond=None)
        if rank != 3:
            raise ValueError('samples do not constrain all three channels')
        rows.append(row)
        conditions.append(float(condition))
    matrix = np.array(rows)
    residual = (x @ matrix.T - y) / (y + .01)
    return matrix, {'samples': len(x), 'condition': conditions,
                    'weighted_rms': np.sqrt(np.mean(residual ** 2, axis=0)).tolist()}


def calibrated_base(target, body_q14):
    """Identity-filter/unit-tone case of the recovered C2.01 M1 producer."""
    target = array(target, (3, 3), 'target')
    body = array(body_q14, (3, 3), 'body calibration')
    if np.any(body != np.floor(body)) or np.any(body < -32768) or np.any(body > 32767):
        raise ValueError('body calibration must contain signed 16-bit integers')
    base = round_away(1024 * target @ invert(body / 16384))
    accum = base @ body
    # Reject wrapping/narrowing instead of turning it into an accepted profile.
    if np.any(2 * base < -32768) or np.any(2 * base > 32767) or np.any(np.abs(2 * accum) >= 0x40000000):
        raise ValueError('native M1 composition would overflow its rounded domain')
    effective = round_away(accum / 16384)
    if np.any(effective < -4096) or np.any(effective > 4095):
        raise ValueError('effective M1 does not fit signed 13-bit storage')
    return base.astype(int), effective.astype(int)


def log3g10(linear):
    x = np.asarray(linear, dtype=float)
    if not np.isfinite(x).all():
        raise ValueError('nonfinite linear sample')
    # The candidate has the documented nonnegative camera lookup clamp.
    return .224282 * np.log10(1 + 155.975327 * (np.maximum(x, 0) + .01))


def tables(grid, *, linear_per_node, ceiling):
    g = array(grid, (229,), 'knot grid')
    if (g[0] != 0 or np.any(g != np.floor(g)) or np.any(np.diff(g) <= 0)
            or g[-1] > 65536 or not math.isfinite(linear_per_node) or linear_per_node <= 0
            or type(ceiling) is not int or not 0 < ceiling <= 32767):
        raise ValueError('invalid grid, scale or storage ceiling')
    rgb = np.minimum(ceiling, np.floor(32 * 1023 * log3g10(g * linear_per_node) + .5)).astype(int)
    return np.tile(rgb, (6, 1)), (rgb + 4) // 8


def compensation():
    """Quantized constant CPXS inverse of final E * native Y2r.

    Return Pa,Pb,Pc,Pd,Pe,Pf in the published coordinate convention.
    All 32 sectors have the same row, so angular interpolation is immaterial.
    """
    k = invert((E_Q9 / 512) @ (Y2R_Q10 / 1024))
    return round_away(256 * k[[1, 1, 2, 2, 0, 0], [1, 2, 1, 2, 1, 2]]).astype(int)


def cpxs_apply(yuv, rows, origin_degrees):
    """Z8's measured diamond-sector interpolation, in angular ring order.

    The caller must map native storage slots into angular order. This is a
    reference model, not evidence of C2.01's active sector convention.
    """
    yuv = np.asarray(yuv, dtype=float)
    if yuv.ndim != 2 or yuv.shape[1] != 3 or not np.isfinite(yuv).all():
        raise ValueError('invalid CPXS input')
    rows = array(rows, (32, 6), 'CPXS ring')
    if not math.isfinite(origin_degrees):
        raise ValueError('invalid sector origin')
    u, v = yuv[:, 1], yuv[:, 2]
    angle = np.mod(np.arctan2(v, u), 2 * np.pi)
    quadrant = np.floor(angle / (np.pi / 2))
    local = angle - quadrant * (np.pi / 2)
    diamond = 90 * (quadrant + np.sin(local) / (np.cos(local) + np.sin(local)))
    position = np.mod((diamond - origin_degrees) / 11.25, 32)
    first = np.floor(position).astype(int)
    fraction = (position - first)[:, None]
    coeff = (rows[first] * (1 - fraction) + rows[(first + 1) % 32] * fraction) / 256
    a, b, c, d, e, f = coeff.T
    return np.column_stack((yuv[:, 0] + e*u + f*v, a*u + b*v, c*u + d*v))


def cpxs_inverse(values, rows, origin_degrees):
    """Numerical inverse with residual and Jacobian checks; never a blind fit.

    Invert only chroma, then undo its contribution to Y. Failure to converge
    rejects the sample. This local inverse is not a global injectivity proof
    for an arbitrary supplied CPXS table.
    """
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3 or not np.isfinite(values).all():
        raise ValueError('invalid encoded CPXS values')
    result = []
    for value in values:
        x = np.array([0., value[1], value[2]])
        for _ in range(40):
            got = cpxs_apply(x[None], rows, origin_degrees)[0]
            error = got[1:] - value[1:]
            step = max(1e-6, np.max(np.abs(x[1:])) * 1e-6)
            columns = []
            for channel in (1, 2):
                shifted = x.copy()
                shifted[channel] += step
                columns.append((cpxs_apply(shifted[None], rows, origin_degrees)[0, 1:] - got[1:]) / step)
            jacobian = np.array(columns).T
            if np.linalg.cond(jacobian) > 1e6:
                raise ValueError('CPXS inverse has a singular local chroma mapping')
            # A zero residual alone also occurs when a singular mapping has
            # collapsed many inputs to the same neutral output.
            if np.max(np.abs(error)) < 1e-9:
                break
            delta = np.linalg.solve(jacobian, error)
            accepted = False
            for power in range(12):
                trial = x.copy()
                trial[1:] -= delta / (2**power)
                residual = cpxs_apply(trial[None], rows, origin_degrees)[0, 1:] - value[1:]
                if np.linalg.norm(residual) < np.linalg.norm(error):
                    x = trial
                    accepted = True
                    break
            if not accepted:
                raise ValueError('CPXS inverse failed to reduce its residual')
        else:
            raise ValueError('CPXS inverse failed to converge')
        x[0] = value[0] - cpxs_apply(x[None], rows, origin_degrees)[0, 0]
        result.append(x)
    return np.array(result)


def recover_pre_m1(file_codes, *, m1_q10, m2_q9, curve15, grid,
                   cpxs_ring_q8, origin_degrees, y2r_q10, file_ycc_q9):
    """Invert a supplied recording configuration to pre-M1 *node* units.

    Configuration values must come from the same clip. This routine does not
    infer primaries from VUI tags or apply a linear RAW matrix to log samples.
    Plateau/end-clipped curve values are rejected as non-identifiable inputs.
    """
    codes = np.asarray(file_codes, dtype=float)
    if codes.ndim != 2 or codes.shape[1] != 3 or not np.isfinite(codes).all():
        raise ValueError('invalid file-code samples')
    g = array(grid, (229,), 'grid')
    lut = array(curve15, (3, 229), 'channel curves') / 32
    if np.any(np.diff(g) <= 0) or np.any(np.diff(lut, axis=1) < 0):
        raise ValueError('nonmonotonic grid or curve')
    downstream = (array(file_ycc_q9, (3, 3), 'file encoding') / 512
                  @ array(y2r_q10, (3, 3), 'Y2r') / 1024)
    after = (codes - [0, 512, 512]) @ invert(downstream).T
    before = cpxs_inverse(after, cpxs_ring_q8, origin_degrees)
    rgb = before @ invert(array(m2_q9, (3, 3), 'M2') / 512).T
    node = np.empty_like(rgb)
    for channel in range(3):
        curve = lut[channel]
        values = rgb[:, channel]
        if np.any(values <= curve[0] + 1e-8) or np.any(values >= curve[-1] - 1e-8):
            raise ValueError('clipped curve endpoint cannot identify linear input')
        flats = curve[:-1][np.diff(curve) == 0]
        if any(np.any(np.abs(values - flat) < 1e-8) for flat in flats):
            raise ValueError('curve plateau cannot identify linear input')
        node[:, channel] = np.interp(values, curve, g)
    return node @ invert(array(m1_q10, (3, 3), 'M1') / 1024).T


def cpxs_inverse_pixels(values, rows, origin_degrees):
    """Batch inverse for pixel-first analysis, checked against cpxs_inverse.

    Each pixel has an independent line search. Failure rejects the batch;
    no difficult pixel silently keeps an unconverged iterate.
    This retains the scalar model's local, rather than global, inverse scope.
    """
    values = np.asarray(values, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 3 or not len(values)
            or not np.isfinite(values).all()):
        raise ValueError('expected nonempty finite CPXS pixel rows')
    rows = array(rows, (32, 6), 'CPXS ring')
    x = values.copy()
    x[:, 0] = 0
    for _ in range(40):
        got = cpxs_apply(x, rows, origin_degrees)
        error = got[:, 1:] - values[:, 1:]
        step = np.maximum(1e-6, np.max(np.abs(x[:, 1:]), axis=1) * 1e-6)
        columns = []
        for channel in (1, 2):
            shifted = x.copy()
            shifted[:, channel] += step
            columns.append((cpxs_apply(shifted, rows, origin_degrees)[:, 1:]
                            - got[:, 1:]) / step[:, None])
        jacobian = np.stack(columns, axis=-1)
        if np.any(np.linalg.cond(jacobian) > 1e6):
            raise ValueError('singular local CPXS pixel mapping')
        if np.max(np.abs(error)) < 1e-8:
            break
        delta = np.linalg.solve(jacobian, error[..., None])[..., 0]
        norm = np.sum(error ** 2, axis=1)
        pending = norm > 1e-16
        for power in range(12):
            trial = x.copy()
            trial[:, 1:] -= delta / (2 ** power)
            residual = cpxs_apply(trial, rows, origin_degrees)[:, 1:] - values[:, 1:]
            accepted = pending & (np.sum(residual ** 2, axis=1) < norm)
            x[accepted] = trial[accepted]
            pending[accepted] = False
            if not np.any(pending):
                break
        if np.any(pending):
            raise ValueError('CPXS pixel inverse failed to reduce residual')
    else:
        raise ValueError('CPXS pixel inverse did not converge')
    x[:, 0] = values[:, 0] - cpxs_apply(x, rows, origin_degrees)[:, 0]
    return x


def recover_pre_m1_pixels(file_codes, *, m1_q10, m2_q9, curve15, grid,
                          cpxs_ring_q8, origin_degrees, y2r_q10, file_ycc_q9):
    """Recover individual pixels, returning NaN for non-identifiable nodes.

    Average only admitted linear rows. Inverting a region's average encoded
    value biases textured regions even with perfectly matched recordings.
    The supplied configuration still needs an independent target binding.
    """
    codes = np.asarray(file_codes, dtype=float)
    if (codes.ndim != 2 or codes.shape[1] != 3 or not len(codes)
            or not np.isfinite(codes).all()):
        raise ValueError('expected nonempty finite file-code rows')
    g = array(grid, (229,), 'grid')
    lut = array(curve15, (3, 229), 'channel curves') / 32
    if np.any(np.diff(g) <= 0) or np.any(np.diff(lut, axis=1) < 0):
        raise ValueError('nonmonotonic grid or curve')
    downstream = (array(file_ycc_q9, (3, 3), 'file encoding') / 512
                  @ array(y2r_q10, (3, 3), 'Y2r') / 1024)
    after = (codes - [0, 512, 512]) @ invert(downstream).T
    before = cpxs_inverse_pixels(after, cpxs_ring_q8, origin_degrees)
    rgb = before @ invert(array(m2_q9, (3, 3), 'M2') / 512).T
    admitted = np.ones(len(codes), dtype=bool)
    node = np.empty_like(rgb)
    for channel, curve in enumerate(lut):
        values = rgb[:, channel]
        admitted &= (values > curve[0] + 1e-8) & (values < curve[-1] - 1e-8)
        for flat in curve[:-1][np.diff(curve) == 0]:
            admitted &= np.abs(values - flat) >= 1e-8
        node[:, channel] = np.interp(values, curve, g)
    node = node @ invert(array(m1_q10, (3, 3), 'M1') / 1024).T
    node[~admitted] = np.nan
    return node, admitted


def build_profile(camera_to_xyz, raw_from_m1, body_q14, grid, *, linear_per_node, ceiling):
    target = camera_to_rwg(camera_to_xyz, raw_from_m1)
    base, effective = calibrated_base(target, body_q14)
    rgb, nlg = tables(grid, linear_per_node=linear_per_node, ceiling=ceiling)
    return {'schema': 1, 'camera': 'Z6III C2.01', 'recording_qualified': False,
            'input_basis': np.asarray(raw_from_m1).tolist(),
            'linear_per_node': linear_per_node, 'ceiling': ceiling,
            'target_m1': target.tolist(), 'm1_base_q10': base.tolist(),
            'm1_effective_q10': effective.tolist(), 'body_q14': np.asarray(body_q14).tolist(),
            'grid': list(grid), 'rgb15': rgb.tolist(), 'nlg12': nlg.tolist(),
            'm2_q9': E_Q9.tolist(), 'cpxs_q8': np.tile(compensation(), (32, 1)).tolist(),
            'y2r_q10': Y2R_Q10.tolist(), 'file_ycc_q9': E_Q9.tolist(),
            'scope': 'Offline candidate; input basis, node scale, hardware order, clipping, '
                     'codec range and native lifetime need C2.01 qualification.'}


def forward(profile, pre_m1):
    """Floating reference in ten-bit file codes, before codec subsampling.

    Linear interpolation follows the Z8 measurement model. It is deliberately
    not presented as bit-exact C2.01 hardware rounding or a codec emulator.
    NLG is generated and retained but has no independently recovered pixel
    contribution in this model. Only the first member of equal curve pairs is
    needed here; unequal pairs are rejected rather than silently discarded.
    """
    x = np.asarray(pre_m1, dtype=float)
    if x.ndim != 2 or x.shape[1] != 3 or not np.isfinite(x).all():
        raise ValueError('expected finite pre-M1 RGB rows')
    lut = array(profile['rgb15'], (6, 229), 'curves')
    if any(not np.array_equal(lut[2*k], lut[2*k+1]) for k in range(3)):
        raise ValueError('unequal curve pairs need a qualified blend model')
    grid = array(profile['grid'], (229,), 'grid')
    m1 = array(profile['m1_effective_q10'], (3, 3), 'M1') / 1024
    node = (x @ m1.T) / profile['linear_per_node']
    rgb = np.column_stack([np.interp(node[:, k], grid, lut[2*k] / 32) for k in range(3)])
    yuv = rgb @ (array(profile['m2_q9'], (3, 3), 'M2') / 512).T
    rows = array(profile['cpxs_q8'], (32, 6), 'CPXS')
    if not np.all(rows == rows[0]):
        raise ValueError('nonconstant CPXS needs a qualified sector model')
    a, b, c, d, e, f = rows[0] / 256
    cpxs = np.array([[1, e, f], [0, a, b], [0, c, d]])
    output = (array(profile['file_ycc_q9'], (3, 3), 'file encoding') / 512
              @ array(profile['y2r_q10'], (3, 3), 'Y2r') / 1024 @ cpxs)
    return yuv @ output.T + [0, 512, 512]
