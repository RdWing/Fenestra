"""Check two original desktop pixel slices with explicit test inputs.

The host supplies stack locals and absolute values between the slices.
No instruction or called array helper is replaced. This is not a complete
desktop filter run or a camera pixel test.
"""
import argparse
from array import array
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host.desktop_m1_reference import m1_pixel, paired_curves
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X29, UC_ARM64_REG_X0, UC_ARM64_REG_PC

SDK_SHA = '7fe5cfaf4d35c9c4291cd502cd41835089c1a15755ace9bf3431d780cdba8424'
SP, OBJECT, IMPL, RGB = 0x10010000, 0x10020000, 0x11000000, 0x10030000
M1_SPAN = (0x178042c, 0x1780a10)
CURVE_SPAN = (0x1780a38, 0x1781160)
ARRAY_SPAN = (0xfcf9f0, 0xfcfa10)


def verify(path):
    blob = Path(path).read_bytes()
    if hashlib.sha256(blob).hexdigest() != SDK_SHA:
        raise ValueError('desktop SDK identity differs')
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    offset = 32
    for _ in range(struct.unpack_from('<I', blob, 16)[0]):
        kind, size = struct.unpack_from('<II', blob, offset)
        if kind == 0x19:
            address, extent, file_offset, file_size = struct.unpack_from('<4Q', blob, offset + 24)
            if extent:
                u.mem_map(address, (extent + 4095) & ~4095)
                u.mem_write(address, blob[file_offset:file_offset + file_size])
        offset += size
    u.mem_map(0x10000000, 0x100000)
    u.mem_map(IMPL, 0x120000)

    def put(address, value, fmt='Q'):
        u.mem_write(address, struct.pack('<' + fmt, value))

    def get(address, fmt='i'):
        return struct.unpack('<' + fmt, u.mem_read(address, struct.calcsize('<' + fmt)))[0]

    def run(span):
        u.emu_start(span[0], span[1], count=10000)
        if u.reg_read(UC_ARM64_REG_PC) != span[1]:
            raise AssertionError('instruction bound reached')

    v = SP + 0x288
    put(SP + 0x1f0, v)
    put(SP + 0x1f8, OBJECT)
    put(OBJECT + 0x350, IMPL)
    for n, off in enumerate((0xb8, 0xb0, 0xa8)):
        put(v + off, RGB + 2 * n)
    put(v + 0x80, 0, 'I')
    u.reg_write(UC_ARM64_REG_SP, SP)
    u.reg_write(UC_ARM64_REG_X29, SP + 0x520)

    tables = [array('H', (min(32767, x * x // (32 + 8 * n)) for x in range(65536)))
              for n in range(6)]
    for n, table in enumerate(tables):
        # array uses host byte order. Serialize the fixture explicitly.
        u.mem_write(IMPL + 0x2f7d0 + n * 0x20000, struct.pack('<65536H', *table))
    rng = random.Random(0x201111)
    matrix_cases = curve_cases = 0
    witness = None
    for index in range(4096):
        matrix = tuple(rng.randrange(-4096, 4096) for _ in range(9))
        rgb = tuple(rng.randrange(65536) for _ in range(3))
        clip = (0, 1, 32767, 65535)[index % 4]
        if index == 0:
            matrix = (512, 512, 0, 0, 1024, 0, 0, 0, 1024)
            rgb, clip = (100, 900, 0), 0
        elif index == 1:
            matrix, rgb = (1,) * 9, (256,) * 3
        elif index == 2:
            matrix, rgb = (-4096,) * 9, (65535,) * 3
        elif index == 3:
            matrix, rgb = (4095,) * 9, (65535,) * 3
        u.mem_write(IMPL + 0x48, struct.pack('<H9h', clip, *matrix))
        u.mem_write(RGB, struct.pack('<3H', *rgb))
        alpha = (0, 1, 128, 255, 256)[(index // 8) % 5]
        mode = (index // 4) % 2
        offset_value = (0, 93, 32767)[(index // 40) % 3]
        curve_clip = (0, 1, 32767)[(index // 120) % 3]
        if index == 0:
            alpha, mode, offset_value, curve_clip = 256, 0, 0, 0
        u.mem_write(IMPL + 0x5c, struct.pack('<Bx3H', mode, offset_value, curve_clip, alpha))
        run(M1_SPAN)
        original_m1 = tuple(get(v + x) for x in (0x64, 0x60, 0x5c))
        expected_m1 = m1_pixel(rgb, matrix, clip)
        assert original_m1 == expected_m1, (index, original_m1, expected_m1)
        matrix_cases += 1
        # The excluded calls are the platform abs import, not color arithmetic.
        put(v + 0x50, abs(original_m1[0]), 'I')
        put(v + 0x4c, abs(original_m1[1]), 'I')
        u.reg_write(UC_ARM64_REG_X0, abs(original_m1[2]))
        run(CURVE_SPAN)
        original_curve = tuple(get(SP + x, 'h') for x in (0x2be, 0x2b6, 0x2ae))
        expected_curve = paired_curves(expected_m1, tables, alpha, mode, offset_value, curve_clip)
        assert original_curve == expected_curve, (index, original_curve, expected_curve)
        curve_cases += 1
        if index == 0:
            reverse = m1_pixel(paired_curves(rgb, tables, alpha), matrix)
            assert reverse != original_curve
            witness = {'rgb': rgb, 'matrix': matrix, 'm1_then_curves': original_curve,
                       'curves_then_m1': reverse}
    regions = [{'start': hex(a), 'end_exclusive': hex(b),
                'sha256': hashlib.sha256(u.mem_read(a, b - a)).hexdigest()}
               for a, b in (M1_SPAN, CURVE_SPAN, ARRAY_SPAN)]
    grid = struct.unpack('<229I', u.mem_read(0x23ea8d4, 916))
    zr_grid = json.loads((ROOT / 'host/log3g10_reference.json').read_text())['grid']
    assert list(grid[:-1]) == zr_grid[:-1] and grid[-1] == 65536 and zr_grid[-1] == 65535
    return {'passed': True, 'sdk_sha256': SDK_SHA, 'm1_pixel_cases': matrix_cases,
            'paired_curve_cases': curve_cases, 'order_witness': witness, 'regions': regions,
            'grid': grid, 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in ('host/desktop_m1_reference.py', 'host/check_desktop_m1_order.py',
                             'host/log3g10_reference.json')},
            'complete_filter_execution': False, 'camera_pixel_execution': False,
            'modelled_boundary': 'stack inputs and abs results between original slices'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.sdk)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('grid', 'source_sha256')}, indent=2))
