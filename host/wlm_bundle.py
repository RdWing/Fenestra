"""Canonical WLM v4 frontend envelopes for core-owned providers.

This implements the zero-component subset of the checked Z8 bundle format.
Native components are rejected until their composition/lifetime is supported.
"""
import hashlib
import struct
from module_header import validate_package, PACKAGE_LIMIT

HEADER = 192


def identifier(name):
    if not isinstance(name, str) or not 1 <= len(name) <= 15 or any(
            c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in name):
        raise ValueError('canonical module identifier required')
    return name.encode('ascii').ljust(16, b'\0')


def encode_frontend_bundle(frontend, module_id, target):
    frontend = bytes(frontend)
    target = bytes(target)
    if len(target) != 32 or len(frontend) < 128 or struct.unpack_from('<I', frontend, 8)[0] not in (2, 3):
        raise ValueError('service frontend and 32-byte target required')
    validate_package(frontend, target)
    if len(frontend)+HEADER > PACKAGE_LIMIT:
        raise ValueError('frontend bundle exceeds managed package capacity')
    h = bytearray(HEADER)
    h[:8] = b'FENESTRA'
    struct.pack_into('<4I', h, 8, 4, HEADER, 1, 1)
    h[24:56] = target
    h[56:88] = hashlib.sha256(frontend).digest()
    struct.pack_into('<4I', h, 88, HEADER+len(frontend), 0, HEADER, len(frontend))
    h[104:136] = h[56:88]
    struct.pack_into('<4I', h, 136, HEADER, 0, 64, 1)
    h[152:168] = identifier(module_id)
    return bytes(h)+frontend


def decode_frontend_bundle(data, target, module_id=None, capabilities=0x7f0000):
    data = bytes(data)
    if not HEADER+128 < len(data) <= PACKAGE_LIMIT or data[:8] != b'FENESTRA':
        raise ValueError('invalid frontend bundle extent or magic')
    if struct.unpack_from('<4I', data, 8) != (4, HEADER, 1, 1) or data[24:56] != target:
        raise ValueError('bundle contract or target mismatch')
    if struct.unpack_from('<4I', data, 88) != (len(data), 0, HEADER, len(data)-HEADER):
        raise ValueError('noncanonical frontend extent')
    if struct.unpack_from('<4I', data, 136) != (HEADER, 0, 64, 1):
        raise ValueError('native component composition is not supported')
    try:
        name = data[152:168].split(b'\0', 1)[0].decode('ascii')
    except UnicodeError as error:
        raise ValueError('invalid module identifier') from error
    if identifier(name) != data[152:168] or any(data[168:HEADER]):
        raise ValueError('noncanonical identifier or reserved fields')
    if module_id is not None and name != module_id:
        raise ValueError('bundle identifier differs from filename')
    front = data[HEADER:]
    digest = hashlib.sha256(front).digest()
    if digest != data[56:88] or digest != data[104:136]:
        raise ValueError('bundle checksum mismatch')
    if struct.unpack_from('<I', front, 8)[0] not in (2, 3):
        raise ValueError('nested or native frontend is not supported')
    metadata = validate_package(front, target, capabilities=capabilities)
    return dict(metadata, package_bytes=len(data), bundle_id=name, frontend=front)
