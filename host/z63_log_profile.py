"""ZR-derived Log3G10 producer base; retain native per-body composition.

The standalone C2.01 patch establishes the producer's base-row contract.
This independently computes that row from the attributed RAW matrix and
RWG primaries. It does not cancel calibration or supply a fitted pixel basis.
"""
import hashlib
import struct

import numpy as np

from host.r3dne_profile import load
from host.rwg_pipeline import invert, round_away, rwg_to_xyz
from host.rwg_pipeline import tables, compensation, E_Q9
from host.log3g10_reference import reference

EXPECTED_BASE = (825, 238, -22, -28, 1106, -36, 5, 26, 1011)


def producer_tables():
    """Independently generate the five resident Log3G10 producer inputs.

    Use the standalone patch's knot scale and highlight ceiling explicitly.
    The ceiling is a plateau, not a calibrated Z6III highlight range.
    """
    rgb, nlg = tables(reference()['grid'], linear_per_node=.00045, ceiling=24693)
    return (
        struct.pack('<9h', *profile()['m1_base_q10']),
        struct.pack('<9h', *E_Q9.flat),
        struct.pack('<687H', *rgb[:3].flat),
        struct.pack('<229H', *nlg),
        struct.pack('<192h', *list(compensation()) * 32),
    )


def generate_header():
    names = ('m1', 'm2', 'rgb', 'nlg', 'cpxs')
    return '\n'.join(
        '_Alignas(16) static const unsigned char fx_z63_log_' + name
        + '[' + str(len(blob)) + ']={' + ','.join(map(str, blob)) + '};'
        for name, blob in zip(names, producer_tables())) + '\n'


def profile():
    source, payload = load()
    camera = np.array(struct.unpack('>9f', payload[1:])).reshape(3, 3)
    # Retain the standalone patch's explicit 1042/1024 scale convention.
    unrounded = 1042 * (invert(rwg_to_xyz()) @ camera)
    base = tuple(int(x) for x in round_away(unrounded).flat)
    if base != EXPECTED_BASE:
        raise ValueError('ZR-derived Log3G10 producer base differs')
    packed = struct.pack('<9h', *base)
    return {
        'schema': 'fenestra.z63-log-producer/v1',
        'target': 'z63-c201',
        'source_profile': source['profile'],
        'matrix_sha256': hashlib.sha256(payload).hexdigest(),
        'm1_base_q10': list(base),
        'm1_base_hex': packed.hex(),
        'scale': [1042, 1024],
        'body_policy': 'preserve-original-producer-composition',
        'physical_color_qualified': False,
    }


def body_product(base, body_q14):
    """Expected identity-filter/unit-tone result, not a replacement producer.

    Other filters and tone scales must go through the original producer.
    Reject overflow rather than certifying native narrowing as valid color.
    """
    a = np.asarray(base)
    b = np.asarray(body_q14)
    for values in (a, b):
        if (values.shape != (9,) or not np.isfinite(values).all()
                or np.any(values != np.floor(values))
                or np.any(values < -32768) or np.any(values > 32767)):
            raise ValueError('expected nine signed 16-bit integers')
    accum = a.astype(np.int64).reshape(3, 3) @ b.astype(np.int64).reshape(3, 3)
    if np.any(np.abs(2 * accum) >= 0x40000000):
        raise ValueError('native rounded accumulator overflow')
    effective = round_away(accum / 16384).astype(int)
    if np.any(effective < -4096) or np.any(effective > 4095):
        raise ValueError('effective M1 exceeds signed 13-bit storage')
    return tuple(int(x) for x in effective.flat)
