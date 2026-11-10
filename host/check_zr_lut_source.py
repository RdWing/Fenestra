#!/usr/bin/env python3
"""Check the ZR LUT source with static data and original instructions.

The caller supplies synthetic property values and record storage. This test
does not execute an active camera route or establish a recording transform.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import (
    UC_ARM64_REG_PC, UC_ARM64_REG_X0, UC_ARM64_REG_SP,
    UC_ARM64_REG_LR, UC_ARM64_REG_CPACR_EL1,
)

BASE = 0x40160000
FIRMWARE_PINS = {
    'zr': '9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f',
    'z63': '236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87',
}
DATA_LAYOUTS = {'zr': (0x4f57000, 0x472000), 'z63': (0x5095000, 0x3d9028)}


class Original:
    """Load a pinned MAIN payload into isolated ARM64 test memory."""

    def __init__(self, path, model):
        self.blob = Path(path).read_bytes()
        if hashlib.sha256(self.blob).hexdigest() != FIRMWARE_PINS[model]:
            raise ValueError('Firmware identity differs: ' + model)
        self.u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.u.mem_map(BASE, (len(self.blob) + 4095) & ~4095)
        self.u.mem_write(BASE, self.blob)
        self.u.mem_map(0xa02800000, 0x4000000)
        start, size = DATA_LAYOUTS[model]
        self.u.mem_write(0xa02808000, self.blob[start:start + size])
        self.u.mem_map(0x100000, 0x100000)
        self.u.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)

    def put(self, address, value, fmt='Q'):
        self.u.mem_write(address, struct.pack('<' + fmt, value))

    def get(self, address, fmt='Q'):
        return struct.unpack('<' + fmt, self.u.mem_read(address, struct.calcsize('<' + fmt)))[0]

    def run(self, pc, *args):
        self.u.reg_write(UC_ARM64_REG_SP, 0x1fe000)
        self.u.reg_write(UC_ARM64_REG_LR, 0x1ffff0)
        for i in range(8):
            self.u.reg_write(UC_ARM64_REG_X0 + i, args[i] if i < len(args) else 0)
        self.u.emu_start(pc, 0x1ffff0, count=1000000)
        if self.u.reg_read(UC_ARM64_REG_PC) != 0x1ffff0:
            raise AssertionError('Instruction bound reached')
        return self.u.reg_read(UC_ARM64_REG_X0)

    def region(self, address, length):
        data = self.blob[address - BASE:address - BASE + length]
        return {'address': hex(address), 'bytes': length, 'sha256': hashlib.sha256(data).hexdigest()}


def write_result(path, result):
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')


def loader_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


NATIVE = 0xa029d0eb0
LENGTH = 0x7340
LUT_SHA = 'eec705a96e27a9a062621949190968effbb46c46ef182896d75121706c50d921'
COEFFICIENTS = (306, 601, 117, -173, -339, 512, 512, -429, -83, 0, 0, 0)


def cube(size):
    lines = [f'LUT_3D_SIZE {size}', '']
    for b in range(size):
        for g in range(size):
            for r in range(size):
                lines.append(' '.join(f'{v / (size - 1):.8f}' for v in (r, g, b)))
    return ('\n'.join(lines) + '\n').encode()


def expected_identity():
    data = bytearray()
    for b in range(17):
        for g in range(17):
            for r in range(17):
                rgb = [int(v / 16 * 4095) for v in (r, g, b)]
                ycc = [sum(COEFFICIENTS[row * 3 + i] * rgb[i] for i in range(3)) >> 10
                       for row in range(3)]
                ycc[1] += 2048
                ycc[2] += 2048
                data.extend(struct.pack('<3H', *(max(0, min(4095, v)) for v in ycc)))
    return bytes(data) + bytes(26)


def verify(zr_path, output):
    z = Original(zr_path, 'zr')
    native = bytes(z.u.mem_read(NATIVE, LENGTH))
    assert hashlib.sha256(native).hexdigest() == LUT_SHA
    assert bytes(z.u.mem_read(NATIVE - 0xbc, 8)) == b'REC.709\0'
    assert z.get(NATIVE - 0xc0, 'I') == LENGTH
    assert native[17**3 * 6:] == bytes(26)
    assert struct.unpack('<12h', bytes(z.u.mem_read(0x444177f0, 24))) == COEFFICIENTS
    sync = struct.unpack('<24h', bytes(z.u.mem_read(0xa02b96d90, 48)))
    assert sync == (1024, 0, 1436, 1024, -352, -731, 1024, 1815, 0, 128, 32, 128, *COEFFICIENTS)
    ids = struct.unpack('<10I', bytes(z.u.mem_read(0x44417808, 40)))
    assert ids == tuple(range(0x2200, 0x220a))
    assert z.get(0xa02c0da48 + 0x370, 'I') == 0x0400262e
    assert z.get(0x442fae98) == 0xa03fea69c
    assert z.get(0x442f91a0) == 0xa0410fcc0
    getter_cases = []
    for selected in (0, 1, 9, 10, 0xffffffff):
        for state in ('null', 'empty', 'valid'):
            for i in range(10):
                p = 0x160000 + i * 0x8000
                z.put(0xa05340ec0 + i * 8, 0 if state == 'null' else p)
                z.put(p, LENGTH if state == 'valid' else 0, 'I')
            z.put(0xa0410fcc0, selected, 'I')
            result = z.run(0x4129ca58)
            expected = 0x160000 + selected * 0x8000 + 0xc0 if selected < 10 and state == 'valid' else 0
            assert result == expected, (selected, state, result, expected)
            getter_cases.append({'selected': selected, 'record': state, 'result': hex(result)})
    # The complete parser uses the original line reader and C runtime helpers.
    # No native helper is replaced. A bound catches malformed input loops.
    z.u.mem_map(0x30000000, 0x1000000)
    parser_cases = []
    from unicorn import UC_HOOK_CODE
    progress = []
    def read_line(uc, address, size, data):
        progress.append(uc.reg_read(UC_ARM64_REG_X0 + 2))
    z.u.hook_add(UC_HOOK_CODE, read_line, begin=0x4130c320, end=0x4130c320)
    for size in (17, 33, 65):
        source = cube(size)
        z.u.mem_write(0x30000000, source)
        z.u.mem_write(0x30e00000, b'\xa5' * (LENGTH + 32))
        # Original.run initializes registers; this call needs a larger bound.
        from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_LR
        z.u.reg_write(UC_ARM64_REG_SP, 0x1fe000)
        z.u.reg_write(UC_ARM64_REG_LR, 0x1ffff0)
        for i, v in enumerate((0x30000000, len(source), 0x444177f0, 0x30e00010)):
            z.u.reg_write(UC_ARM64_REG_X0 + i, v)
        z.u.emu_start(0x4130c3c0, 0x1ffff0, count=1000000000)
        assert z.u.reg_read(UC_ARM64_REG_PC) == 0x1ffff0, f'parser instruction bound reached at {z.u.reg_read(UC_ARM64_REG_PC):#x}; lines={len(progress)}; offset={progress[-1] if progress else None}'
        result = z.u.reg_read(UC_ARM64_REG_X0) & 0xffffffff
        assert result == 0, (size, hex(result))
        actual = bytes(z.u.mem_read(0x30e00010, LENGTH))
        assert actual == expected_identity(), (size, next((i for i,(a,b) in enumerate(zip(actual, expected_identity())) if a != b), None))
        assert bytes(z.u.mem_read(0x30e00000, 16)) == b'\xa5' * 16
        assert bytes(z.u.mem_read(0x30e00010 + LENGTH, 16)) == b'\xa5' * 16
        parser_cases.append({'grid': size, 'source_sha256': hashlib.sha256(source).hexdigest(),
                             'source_bytes': len(source), 'output_sha256': hashlib.sha256(actual).hexdigest()})
        print('parser passed', size, flush=True)
    result = {'passed': True, 'firmware_sha256': hashlib.sha256(z.blob).hexdigest(),
              'native_lut_address': hex(NATIVE), 'native_lut_sha256': LUT_SHA,
              'getter_cases': getter_cases, 'parser_cases': parser_cases,
              'native_lut_neutral_y': [struct.unpack_from('<H', native, 6*i*(1+17+289))[0] for i in range(17)],
              'native_lut_sample_bytes': 17**3*6, 'padding_bytes': 26,
              'rgb_to_ycc_coefficients_q10': COEFFICIENTS, 'sync_coefficients_s16': sync,
              'regions': [z.region(a, n) for a,n in ((0x4129ca58, 0x60), (0x41205a4c, 0xdc),
                  (0x4130c3c0, 0x4c8), (0x4129c7ac, 0x258), (0x41114bf4, 0x40))],
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limits': ['Synthetic property and memory inputs.', 'No active route, pixel hardware, recording, or physical-camera qualification.']}
    write_result(output, result)
    print(json.dumps({'passed': True, 'getter_cases': len(getter_cases), 'parser_cases': len(parser_cases)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zr', type=Path, required=True, help='Pinned ZR C1.11 MAIN payload')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.zr, args.output)
