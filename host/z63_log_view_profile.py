"""Z6III internal-panel Log3G10 monitoring matrices, independent of recording.

The rear display follows the stock 709 drive convention. The EVF additionally
uses C2.01's original normal-view correction. This specifies signal conversion,
not measured panel primaries or perceptual calibration. Tone curves are separate.
"""
import struct
import numpy as np
from host.rwg_pipeline import invert, round_away, rwg_to_xyz

C6 = (731, 265, 28, 44, 984, -4, 16, 70, 938)


def matrix_record(coefficients):
    values = tuple(coefficients)
    if len(values) != 9 or any(type(x) is not int or not -2048 <= x <= 2047 for x in values):
        raise ValueError('view-assist coefficients must fit signed 12-bit fields')
    return b'\x01\x01' + struct.pack('<9h', *values) + b'\x01\x00\x00\x00'


def matrices(c6):
    if tuple(c6) != C6:
        raise ValueError('C2.01 viewfinder correction differs')
    primaries = np.array(((.64,.33), (.30,.60), (.15,.06)))
    columns = np.array((primaries[:,0]/primaries[:,1], np.ones(3),
                        (1-primaries.sum(axis=1))/primaries[:,1]))
    white = np.array((.3127/.329, 1, (1-.3127-.329)/.329))
    rgb709 = columns * (invert(columns) @ white)
    rear = invert(rgb709) @ rwg_to_xyz()
    evf = np.array(c6).reshape(3,3)/1024 @ rear
    return tuple(matrix_record(tuple(int(v) for v in round_away(m*1024).flat)) for m in (rear, evf))
