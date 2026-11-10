"""Load the pinned ZR metadata matrix used by the C2.01 RAW candidate."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT/'modules/r3dne/profile.json'
MATRIX_SHA256 = '69ea56695435e553b8d3eebae0cc2b488306564f536f2c04ca73585e51431193'
BLUE_COMMIT = '6ee37b7bb95074592c8989a96eaafc7ab4c23a51'


def load(path=PROFILE):
    profile = json.loads(Path(path).read_text())
    matrix = profile['matrix']
    value = bytes.fromhex(matrix['hex'])
    if (profile['schema'] != 'fenestra.r3dne-matrix-profile/v1'
            or profile['external_source']['commit'] != BLUE_COMMIT
            or matrix['nrmt_tag'] != '0x01900012' or profile['profile_id'] != 1
            or len(value) != 37 or value[0] != 0 or matrix['leading_byte'] != 0
            or matrix['bytes'] != 37 or matrix['layout'] != 'row-major'
            or hashlib.sha256(value).hexdigest() != MATRIX_SHA256
            or matrix['sha256'] != MATRIX_SHA256
            or list(struct.unpack('>9f', value[1:])) != matrix['coefficients']):
        raise ValueError('ZR metadata matrix profile differs')
    return profile, value
