"""Check linked text binding under synthetic native widget operations.

No original firmware executes. Full-system menu tests remain separate.
"""
import argparse
import json
from pathlib import Path
import struct
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
import unicorn.arm64_const as arm


def verify(build):
    build = Path(build)
    report = json.loads((build / 'probe.json').read_text())
    code = (build / 'probe.bin').read_bytes()
    code_base = report['symbols'].get('fx_z63_core_begin', 0x40910000)
    cases = []
    for kind, enabled, missing, current, expected in [
        (2, 1, False, True, 0), (0, 1, False, True, 0),
        (3, 1, False, True, 2), (2, 0, False, True, 0),
        (2, 1, True, True, 2), (2, 1, False, False, 2),
    ]:
        cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        cpu.mem_map(code_base, (len(code) + 4095) & ~4095)
        cpu.mem_write(code_base, code)
        cpu.mem_map(0x800000, 0x20000)
        cpu.mem_map(0x900000, 0x4000)
        cpu.mem_map(0xa00010000, 0x6000)
        page, content, row, value, profile = [0xa00010000 + 4096 * i for i in range(5)]
        functions = [0x900000 + 16 * i for i in range(9)]
        cpu.mem_write(page + 32, struct.pack('<Q', content))
        cpu.mem_write(row + 0x48, struct.pack('<Q', 0x900700))
        cpu.mem_write(row + 8, struct.pack('<II', 3386, 2))
        cpu.mem_write(value + 8, struct.pack('<II', 0, kind))
        cpu.mem_write(profile, struct.pack('<7Q3I4x3Q',
            *functions[:6], 0x900700, 0x4dc0, 0x1c0, 0x118, functions[6], 0, 0))
        for function in functions:
            cpu.mem_write(function, struct.pack('<I', 0xd65f03c0))
        observed = {'disabled': [], 'set_text': 0}

        def read32(address):
            return struct.unpack('<I', cpu.mem_read(address, 4))[0]

        def callback(mu, pc, size, context):
            x0 = mu.reg_read(arm.UC_ARM64_REG_X0)
            x1 = mu.reg_read(arm.UC_ARM64_REG_X1)
            if pc == functions[0]:
                mu.reg_write(arm.UC_ARM64_REG_X0, page if current else 0)
            elif pc == functions[1]:
                assert x0 == 0x7f50 and x1 == content
                mu.reg_write(arm.UC_ARM64_REG_X0, row)
            elif pc == functions[2]:
                assert x0 == row and x1 == 0x4dc0
                mu.reg_write(arm.UC_ARM64_REG_X0, 0 if missing else value)
            elif pc == functions[3]:
                observed['disabled'].append((x0, x1))
            elif pc == functions[4]:
                assert x0 == value and x1 == 3390
                assert mu.reg_read(arm.UC_ARM64_REG_X2) == 2
                observed['set_text'] += 1
                # A source-3 widget refuses source-2 text. The linked caller
                # must detect refusal rather than report a successful binding.
                if read32(value + 12) in (0, 2):
                    mu.mem_write(value + 8, struct.pack('<II', x1, 2))
            elif pc == functions[6]:
                assert x0 == value and x1 == 2

        cpu.hook_add(UC_HOOK_CODE, callback)
        cpu.reg_write(arm.UC_ARM64_REG_SP, 0x810000)
        cpu.reg_write(arm.UC_ARM64_REG_X30, 0x903000)
        for index, argument in enumerate((profile, page, 0x7f50, 3386, 3390, enabled, 0)):
            cpu.reg_write(getattr(arm, 'UC_ARM64_REG_X' + str(index)), argument)
        cpu.emu_start(report['symbols']['fx_native_text_prepare'], 0x903000, count=10000)
        result = cpu.reg_read(arm.UC_ARM64_REG_X0)
        if result != expected:
            raise ValueError('text binding result differs: ' + repr((kind, enabled, missing, current, result)))
        if result == 0:
            assert read32(value + 8) == 3390 and read32(value + 12) == 2
            assert observed['disabled'] == [(row, 1 - enabled), (value, 1 - enabled)]
        cases.append(dict(source_kind=kind, enabled=enabled, missing=missing,
                          current_page=current, result=result, matched=True))
    return dict(passed=True, cases=cases, candidate_sha256=report['candidate_sha256'],
                qualification='Actual linked text helper with synthetic native widget operations. No original firmware calls, full-system or physical acceptance.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.build), indent=2))


if __name__ == '__main__':
    main()
