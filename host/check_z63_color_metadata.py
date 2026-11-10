"""Run C2.01 color selectors and the metadata setter with bounded copy fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC

SHA = '236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87'


def check(path):
    blob = Path(path).read_bytes()
    if hashlib.sha256(blob).hexdigest() != SHA:
        raise ValueError('C2.01 MAIN identity differs')
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    base = 0x40160000
    u.mem_map(base, (len(blob)+4095) & ~4095)
    u.mem_write(base, blob)
    u.mem_map(0x100000, 0x10000)
    stop = 0x10fff0
    def put(address, fmt, *values):
        u.mem_write(address, struct.pack('<'+fmt, *values))
    def get(address, fmt):
        return struct.unpack('<'+fmt, u.mem_read(address, struct.calcsize('<'+fmt)))[0]
    def run(pc, *args):
        u.reg_write(UC_ARM64_REG_SP, 0x10f000)
        u.reg_write(UC_ARM64_REG_LR, stop)
        for i in range(8):
            u.reg_write(UC_ARM64_REG_X0+i, args[i] if i < len(args) else 0)
        u.emu_start(pc, stop, count=10000)
        if u.reg_read(UC_ARM64_REG_PC) != stop:
            raise AssertionError('instruction limit reached')
        return u.reg_read(UC_ARM64_REG_X0)
    selector_cases = 0
    records = []
    for fn, width in [(0x403502e0, 10), (0x40350330, 11), (0x40d1ae78, 10)]:
        for selection in (0, 1, 2, 0xffffffff):
            put(0x100000, 'Q', 0xdeadbeef)
            put(0x100010, 'I', 0xffffffff)
            run(fn, selection, 0x100000, 0x100010)
            ptr, size = get(0x100000, 'Q'), get(0x100010, 'I')
            if selection > 1:
                assert ptr == size == 0
            else:
                assert size == width
                record = bytes(u.mem_read(ptr, size))
                assert record[:4] == (b'nclc' if width == 10 else b'nclx')
                assert struct.unpack('>HHH', record[4:10]) == ((1, 1, 1) if selection == 0 else (9, 18, 9))
                records.append(dict(function=hex(fn), selection=selection, pointer=hex(ptr), hex=record.hex()))
            selector_cases += 1
    for fn in (0x40350380, 0x40d1aee8):
        put(0x100000, 'Q', 0xdeadbeef)
        put(0x100010, 'I', 0xffffffff)
        run(fn, 0x100000, 0x100010)
        assert get(0x100000, 'Q') == get(0x100010, 'I') == 0
        selector_cases += 1
    writer, color, gamma, source = 0x101000, 0x102010, 0x103010, 0x104000
    copy_calls = []
    fail_copy = [False]
    def copy_fixture(uc, pc, size, user):
        dst, src, count = [uc.reg_read(UC_ARM64_REG_X0+i) for i in range(3)]
        assert count <= 64
        copy_calls.append((dst, src, count))
        if not fail_copy[0]:
            uc.mem_write(dst, bytes(uc.mem_read(src, count)))
        uc.reg_write(UC_ARM64_REG_X0, 3 if fail_copy[0] else 0)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE, copy_fixture, begin=0x40ce5c60, end=0x40ce5c60)
    u.mem_write(source, bytes(range(80)))
    setter_cases = 0
    def reset():
        u.mem_write(writer, b'\xa5'*0x600)
        put(writer+0x598, 'Q', color)
        put(writer+0x5a8, 'Q', gamma)
        u.mem_write(color-16, b'\xa5'*96)
        u.mem_write(gamma-16, b'\xa5'*48)
        copy_calls.clear()
    for cptr, clen, gptr, glen in [(source, 64, source+64, 16),
                                  (source, 10, 0, 0), (0, 64, 0, 16),
                                  (source, 0, source+64, 0)]:
        reset()
        assert run(0x40cef0e0, writer, cptr, clen, gptr, glen) == 0
        assert get(writer+0x5a0, 'I') == (clen if cptr else 0)
        assert get(writer+0x5b0, 'I') == (glen if gptr else 0)
        expected_calls = []
        for dst, src, count in ((color, cptr, clen), (gamma, gptr, glen)):
            if src and count:
                expected_calls.append((dst, src, count))
                assert bytes(u.mem_read(dst, count)) == bytes(u.mem_read(src, count))
        assert copy_calls == expected_calls
        assert bytes(u.mem_read(color-16, 16)) == b'\xa5'*16
        assert bytes(u.mem_read(color+64, 16)) == b'\xa5'*16
        assert bytes(u.mem_read(gamma-16, 16)) == b'\xa5'*16
        assert bytes(u.mem_read(gamma+16, 16)) == b'\xa5'*16
        setter_cases += 1
    for ctx, clen, glen in [(0, 10, 0), (writer, 65, 0), (writer, 10, 17)]:
        reset()
        before = bytes(u.mem_read(writer, 0x600))
        assert run(0x40cef0e0, ctx, source, clen, source+64, glen) == 3
        assert bytes(u.mem_read(writer, 0x600)) == before and not copy_calls
        setter_cases += 1
    reset()
    fail_copy[0] = True
    assert run(0x40cef0e0, writer, source, 10, source+64, 16) == 0
    assert get(writer+0x5a0, 'I') == 10 and get(writer+0x5b0, 'I') == 16
    assert bytes(u.mem_read(color, 64)) == b'\xa5'*64
    assert bytes(u.mem_read(gamma, 16)) == b'\xa5'*16
    setter_cases += 1
    return dict(firmware_sha256=SHA, selector_cases=selector_cases, setter_cases=setter_cases,
                records=records, failed_copy_still_publishes_lengths=True,
                copy_service='Substitute bounded memory copy, including a failed-copy case.',
                firmware_boot=False, recording_qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.payload), indent=2))
