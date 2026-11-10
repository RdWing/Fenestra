"""Offline ZR curve reproduction. Does not qualify a camera pixel path."""
import ctypes
import ctypes.util
import json
import math
from pathlib import Path
import struct

DATA = Path(__file__).with_suffix('.json')


def reference():
    return json.loads(DATA.read_text())


def curve(grid, ratio, constants):
    if not math.isfinite(ratio) or abs(ratio) > 32:
        raise ValueError('ratio outside the offline test domain')
    if any(type(k) is not int or not 0 <= k <= 65535 for k in grid):
        raise ValueError('grid must contain unsigned 16-bit integers')
    lib = ctypes.CDLL(ctypes.util.find_library('m') or None)
    log = lib.log10f
    log.argtypes = [ctypes.c_float]
    log.restype = ctypes.c_float
    scale, gray, c, b, a = constants
    out = []
    for k in grid:
        x = k / (scale * 2.0 ** (0.5-ratio)) * gray
        y = float(log(ctypes.c_float(1.0 + b * (x+c))))
        out.append(min(32767, int(32768*a*y+0.5)))
    return out


def matrix(blob):
    if len(blob) != 37 or blob[0] != 0:
        raise ValueError('expected a zero prefix and nine big-endian floats')
    values = struct.unpack('>9f', blob[1:])
    if not all(math.isfinite(x) for x in values):
        raise ValueError('nonfinite matrix coefficient')
    return values


def verify():
    d = reference()
    for vector in d['vectors']:
        got = curve(d['grid'], vector['ratio'], d['constants'])
        if got != vector['values']:
            raise ValueError('curve differs from original-execution reference')
    values = matrix(bytes.fromhex(d['matrix_hex']))
    white = [sum(values[i:i+3]) for i in (0,3,6)]
    if any(abs(a-b) >= 0.002 for a,b in zip(white,(0.9505,1.0,1.089))):
        raise ValueError('matrix does not map unit white to D65')
    return {'curve_samples':687,'matrix_coefficients':list(values),
            'unit_white_xyz':white,'camera_qualified':False}


if __name__ == '__main__':
    print(json.dumps(verify(),indent=2))
