#!/usr/bin/env python3
"""Compare M2 factorizations as hypotheses, without assigning a pixel basis."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct

REFERENCE = Path(__file__).with_name('log3g10_reference.json')
SOURCE_COMMIT = '6ee37b7bb95074592c8989a96eaafc7ab4c23a51'
REFERENCE_SHA = 'c15fc88a01206c49915d7f94d43631a22743f13150659180bc18b15c98fc9d14'
RED_PDF_SHA = 'd3e6207d57aaad0e48b1c04d3c5e3c46ffe83d5f991ac4f3ed135b135133bd36'
SDK_SHA = '7fe5cfaf4d35c9c4291cd502cd41835089c1a15755ace9bf3431d780cdba8424'
SDK_DECODER_SHA = '7483494848fc1572cbd8a6cf7ca6e123228cc6eb3c56fbf966f9e6079cfbf85f'
SDK_DECODER_COEFFICIENTS = (1.0, 0.0, 1.4021, 1.0, -.3455, -.7146, 1.0, 1.7712, 0.0)


def matrix(flat):
    return [list(flat[i:i+3]) for i in range(0, 9, 3)]


def multiply(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def inverse(a):
    aug = [a[i][:] + [int(i == j) for j in range(3)] for i in range(3)]
    for i in range(3):
        pivot = max(range(i, 3), key=lambda j: abs(aug[j][i]))
        aug[i], aug[pivot] = aug[pivot], aug[i]
        scale = aug[i][i]
        assert abs(scale) > 1e-12
        aug[i] = [v/scale for v in aug[i]]
        for j in range(3):
            if i != j:
                scale = aug[j][i]
                aug[j] = [x - scale*y for x, y in zip(aug[j], aug[i])]
    return [row[3:] for row in aug]


def ycc(kr, kb):
    kg = 1 - kr - kb
    return [[kr, kg, kb], [-kr/(2*(1-kb)), -kg/(2*(1-kb)), .5],
            [.5, -kg/(2*(1-kr)), -kb/(2*(1-kr))]]


def error(a, b):
    e = [abs(a[i][j]-b[i][j]) for i in range(3) for j in range(3)]
    return {'max_abs': max(e), 'rms': (sum(v*v for v in e)/9)**.5}


def mv(a, x):
    return [sum(row[j]*x[j] for j in range(3)) for row in a]


def log3(x):
    x += .01
    return 15.1927*x if x < 0 else .224282*math.log10(1 + 155.975327*x)


def verify(source, output, red_paper=None):
    source = Path(source)
    if hashlib.sha256(source.read_bytes()).hexdigest() != REFERENCE_SHA:
        raise ValueError('Matrix reference identity differs')
    reference = json.loads(source.read_text())
    if reference['source_commit'] != SOURCE_COMMIT:
        raise ValueError('Matrix source identity differs')
    if red_paper is not None and hashlib.sha256(Path(red_paper).read_bytes()).hexdigest() != RED_PDF_SHA:
        raise ValueError('RED paper identity differs')
    camera_xyz = matrix(reference['matrix_xyz_d65'])
    xyz_rwg = matrix([1.412807, -.177523, -.151771, -.486203, 1.290697, .157401,
                      -.037139, .286376, .687680])
    rwg_2020 = matrix([1.180431, -.094040, -.086391, -.028017, 1.311442, -.283425,
                       -.074360, -.362078, 1.436437])
    camera_rwg = multiply(xyz_rwg, camera_xyz)
    camera_2020 = multiply(rwg_2020, camera_rwg)
    matrices = {'camera_to_rwg_from_metadata': camera_rwg,
                'camera_to_2020_from_metadata': camera_2020}
    encodings = {'601_full': ycc(.299, .114), '709_full': ycc(.2126, .0722),
                 '2020_full': ycc(.2627, .0593),
                 'zr_lut_q10': matrix([v/1024 for v in (306,601,117,-173,-339,512,512,-429,-83)])}
    native = {'nlog_hlg': matrix([v/512 for v in (126,435,-49,-64,-347,411,248,-217,-31)]),
              'stock_tone3': matrix([v/512 for v in (200,310,3,-65,-504,569,480,-484,4)])}
    candidates = {}
    for tone, m2 in native.items():
        for encoding, e in encodings.items():
            factored = multiply(inverse(e), m2)
            candidates[tone + '/' + encoding] = {'rgb_factor': factored,
                'unit_white': mv(factored, [1,1,1]),
                'comparisons': {name: error(factored, a) for name, a in matrices.items()}}
    # These numerical coefficients reproduce the pinned desktop data block.
    # The actual decoder receives CPXS output, not the immediate M2 output.
    decoder_bytes = struct.pack('<9d', *SDK_DECODER_COEFFICIENTS)
    if hashlib.sha256(decoder_bytes).hexdigest() != SDK_DECODER_SHA:
        raise ValueError('Desktop decoder coefficient identity differs')
    decoder = matrix(SDK_DECODER_COEFFICIENTS)
    compositions = {}
    for tone, m2 in native.items():
        composed = multiply(decoder, m2)
        compositions[tone] = {'decoder_times_m2_q9': composed,
            'unit_white': [sum(row) for row in composed],
            'comparison_with_metadata_camera_to_rwg': error(composed, camera_rwg)}
    desktop = {
        'evidence': 'Labeled desktop algebraic hypothesis; not the actual complete pixel transform.',
        'sdk_sha256': SDK_SHA,
        'sdk_ycc_to_rgb_address': '0x1f7f590',
        'sdk_ycc_to_rgb_bytes': len(decoder_bytes),
        'sdk_ycc_to_rgb_sha256': SDK_DECODER_SHA,
        'sdk_ycc_to_rgb': decoder,
        'sdk_consumer': {'start': '0x1cfef0', 'end_exclusive': '0x1cffd8',
            'sha256': 'c554b1d681495d37e952e96fbd12d22239d7cd660b15bc572f89cd482266b805'},
        'source_check': 'Serialized numerical constants match the pinned block. This tool does not load or execute the SDK.',
        'reference_sha256': REFERENCE_SHA,
        'matrix_source_commit': SOURCE_COMMIT,
        'red_xyz_to_rwg_6_decimal': xyz_rwg,
        'camera_to_rwg_from_metadata': camera_rwg,
        'm2_divisor_hypothesis': 512,
        'compositions': compositions,
        'limits': ['The named SDK decoder receives output after nonlinear CPXS processing, not directly after M2.',
                   'This composition omits intervening processing and clipping. It tests matrix equality under stated assumptions only.',
                   'Camera hardware domains, tone-3 switch semantics, metadata input basis and WB normalization remain unproved.']}
    # The same linear matrix cannot generally be moved across Log3G10.
    order_cases = []
    for x in ([.18,.18,.18], [.1,.3,.05], [1,.1,.02], [.01,.5,1]):
        first = [log3(v) for v in mv(camera_rwg,x)]
        last = mv(camera_rwg,[log3(v) for v in x])
        order_cases.append({'input': x, 'matrix_then_log': first, 'log_then_matrix': last,
                            'max_abs_difference': max(abs(a-b) for a,b in zip(first,last))})
    result = {'evidence': 'Algebraic hypotheses; no camera pixel-domain assignment.',
              'matrix_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'red_reference': 'https://docs.red.com/955-0187/PDF/915-0187%20Rev-C%20%20%20RED%20OPS,%20White%20Paper%20on%20REDWideGamutRGB%20and%20Log3G10.pdf',
              'red_pdf_sha256': RED_PDF_SHA,
              'red_pdf_checked': red_paper is not None,
              'matrices': matrices, 'm2_q9_hypothesis': native, 'factors': candidates,
              'order_counterexamples': order_cases,
              'desktop_decoder_composition': desktop,
              'limitations': ['M2 divisor512 is a normalization hypothesis from row sums, not hardware semantics.',
                              'Metadata matrix input basis and active WB normalization are not joined to M1.',
                              'A factorization exists for every invertible YCbCr matrix and is not proof of that encoding.']}
    result['source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,indent=2) + '\n')
    print(json.dumps({'camera_to_rwg': camera_rwg,
                      'nlog_2020': candidates['nlog_hlg/2020_full'],
                      'tone3_601': candidates['stock_tone3/601_full'],
                      'desktop_decoder_compositions': compositions,
                      'order': order_cases},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix-reference', type=Path, default=REFERENCE,
                        help='Pinned blue-compressor matrix reference JSON')
    parser.add_argument('--red-paper', type=Path, help='Optional pinned RED Rev C PDF')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.matrix_reference, args.output, args.red_paper)
