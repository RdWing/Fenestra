# SPDX-License-Identifier: MIT
"""Check C2.01 PTP size-list selection and request construction offline.

Original instructions run with supplied setting values and write/state services.
This does not boot firmware or qualify effective settings or recording.
"""
import argparse
from pathlib import Path
import hashlib
import json
import struct
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_SP, UC_ARM64_REG_LR, UC_ARM64_REG_PC

SHA = '236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87'
BASE = 0x40160000
ARRAYS = {1: (0xA029A5CB0, 8), 2: (0xA029A5C08, 21), 3: (0xA029A5C08, 21),
          4: (0xA029A5BA8, 12), 5: (0xA029A5D78, 13), 6: (0xA029A5CF0, 17)}


def check(path):
    blob = Path(path).read_bytes()
    if len(blob) != 88830365 or hashlib.sha256(blob).hexdigest() != SHA:
        raise ValueError('C2.01 MAIN identity differs')
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    u.mem_map(BASE, (len(blob)+4095)&~4095)
    u.mem_write(BASE, blob)
    u.mem_map(0x100000, 0x20000)
    u.mem_map(0xA029A5000, 0x1000)
    u.mem_write(0xA029A5000, blob[0x5232000:0x5233000])
    stop = 0x11fff0
    setting_values = []
    setting_keys = []
    reads, batches, scalars = [], [], []
    batch_result = [1]
    state_gate, mode_gate = [0], [0]

    def hook(uc, pc, size, user):
        args = [uc.reg_read(UC_ARM64_REG_X0+i) for i in range(3)]
        if pc == 0x41003D6C:
            assert args[0] == setting_keys.pop(0)
            value = setting_values.pop(0)
            reads.append((args[0], value))
            uc.reg_write(UC_ARM64_REG_X0, value)
        elif pc == 0x408A52A8:
            assert args[2] == 2
            batches.append((struct.unpack('<2I', uc.mem_read(args[0], 8)),
                            struct.unpack('<2I', uc.mem_read(args[1], 8))))
            uc.reg_write(UC_ARM64_REG_X0, batch_result[0])
        elif pc == 0x408A528C:
            scalars.append((args[0], args[1]))
            uc.reg_write(UC_ARM64_REG_X0, 1)
        elif pc == 0x408A48E0:
            uc.reg_write(UC_ARM64_REG_X0, state_gate[0])
        elif pc == 0x408A4864:
            uc.reg_write(UC_ARM64_REG_X0, mode_gate[0])
        else:
            return
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    for address in (0x41003D6C, 0x408A52A8, 0x408A528C, 0x408A48E0, 0x408A4864):
        u.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)

    def run(pc, arg, values, keys=None):
        reads.clear(); batches.clear(); scalars.clear()
        setting_values[:] = values
        setting_keys[:] = keys if keys is not None else [0x06000F06]*len(values)
        u.reg_write(UC_ARM64_REG_SP, 0x11e000)
        u.reg_write(UC_ARM64_REG_LR, stop)
        u.reg_write(UC_ARM64_REG_X0, arg)
        u.emu_start(pc, stop, count=10000)
        assert u.reg_read(UC_ARM64_REG_PC) == stop
        assert not setting_values and not setting_keys
        return u.reg_read(UC_ARM64_REG_X0)

    provider_cases = []
    for kind in (0, 1, 2, 3, 4, 5, 6, 7, 0xffffffff):
        pointer, count = ARRAYS.get(kind, ARRAYS[2])
        u.mem_write(0x100100, b'\xa5'*8)
        assert run(0x40891174, 0x100100, [kind]) == count
        assert struct.unpack('<Q', u.mem_read(0x100100, 8))[0] == pointer
        assert reads == [(0x06000F06, kind)]
        provider_cases.append(dict(file_type=kind, pointer=hex(pointer), count=count))
    assert run(0x40891174, 0, []) == 0

    def pairs(address, count):
        return dict(struct.iter_unpack('<II', blob[address-BASE:address-BASE+count*8]))

    raster, rates, slow = pairs(0x441e4540, 8), pairs(0x441e4580, 9), pairs(0x441e45c8, 3)
    size_keys = struct.unpack_from('<6I', blob, 0x441e6924-BASE)
    rate_keys = struct.unpack_from('<6I', blob, 0x441e690c-BASE)
    accepted = []
    rejected = 0
    for kind, (pointer, count) in ARRAYS.items():
        words = struct.unpack('<'+'Q'*count, u.mem_read(pointer, count*8))
        for wire in words:
            u.mem_write(0x100000, struct.pack('<Q', wire))
            assert run(0x4088FCE0, 0x100000, [kind]*4) == 0x2001
            expected = (raster[wire >> 32], rates[wire >> 16 & 255])
            assert batches == [((size_keys[kind-1], rate_keys[kind-1]), expected)]
            expected_slow = slow[wire & 255] if wire & 0x3f00 == 0x100 else 0
            assert scalars == ([(0x07000F04, expected_slow)] if kind == 1 else [])
            accepted.append(dict(file_type=kind, wire=f'0x{wire:016X}',
                                 request_keys=[hex(size_keys[kind-1]), hex(rate_keys[kind-1])],
                                 request_values=list(expected)))
        for wire in (0xffffffffffffffff, words[0] | 1):
            u.mem_write(0x100000, struct.pack('<Q', wire))
            assert run(0x4088FCE0, 0x100000, [kind]) == 0x201c
            assert not batches and not scalars
            rejected += 1

    wire = struct.unpack('<Q', u.mem_read(ARRAYS[3][0], 8))[0]
    u.mem_write(0x100000, struct.pack('<Q', wire))
    assert run(0x4088FCE0, 0x100000, [3, 4, 6, 5]) == 0x2001
    assert batches == [((size_keys[3], rate_keys[5]), (7, 4))]
    split_case = dict(setting_reads=list(reads), batch_keys=list(batches[0][0]),
                      batch_values=list(batches[0][1]), return_value='0x2001')
    batch_result[0] = 0
    assert run(0x4088FCE0, 0x100000, [3]*4) == 0x2001
    assert len(batches) == 1
    validator_cases = 0
    wires = {int(row['wire'], 16) for row in accepted}
    for wire in sorted(wires):
        u.mem_write(0x100000, struct.pack('<Q', wire))
        for mode in (0, 1, 2, 3):
            for override in (0, 1):
                values = [mode] + ([override] if mode in (1, 3) else [])
                keys = [0x04002C0C] + ([0x04002C13] if mode in (1, 3) else [])
                raster_word, rate = wire >> 32, wire >> 16 & 255
                limited = (raster_word in (0x15000bd0, 0x17a00d4a, 0x0fc008dc) or
                           raster_word == 0x07800438 and rate in (200, 240))
                rejected_mode = mode in (1, 3) and override != 1 and limited
                assert run(0x4088FA70, 0x100000, values, keys) == (0x200f if rejected_mode else 0x2001)
                assert not batches and not scalars
                validator_cases += 1
    assert run(0x4088FA70, 0, []) == 0x2001
    state_gate[0], mode_gate[0] = 1, 2
    assert run(0x4088FA70, 0x100000, []) == 0x200f
    validator_cases += 2
    spans = [(0x4088FA70, 0x4088FB80), (0x4088FCE0, 0x4088FE80),
             (0x40891174, 0x40891234), (0x408A5074, 0x408A5128),
             (0x40864C58, 0x40864C7C)]
    result = dict(firmware_sha256=SHA, evidence='Original instructions with supplied setting reads and write-service capture. No firmware boot.',
                  provider_cases=provider_cases, provider_null_cases=1,
                  accepted_cases=len(accepted), target_accepted_cases=sum(r['file_type']>=3 for r in accepted),
                  rejected_cases=rejected, split_setting_read_case=split_case,
                  failed_batch_still_returns_success_cases=1, accepted=accepted,
                  validator_cases=validator_cases, validator_unique_wire_values=len(wires),
                  substituted_services=['0x41003D6C setting getter', '0x408A52A8 batch setter', '0x408A528C scalar setter',
                                        '0x408A48E0 state helper for validator only', '0x408A4864 mode helper for validator only'],
                  source_sha256={f'{a:#x}..{z:#x}':hashlib.sha256(blob[a-BASE:z-BASE]).hexdigest() for a,z in spans},
                  scope='PTP list membership, requested-setting construction, and local validator with supplied state. Outer dispatch, effective configuration and encoding are not executed.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main', type=Path, help='Original C2.01 MAIN.raw with the pinned SHA-256.')
    parser.add_argument('--output', type=Path, required=True, help='Path for the JSON result.')
    args = parser.parse_args()
    result = check(args.main)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({key: result[key] for key in (
        'accepted_cases', 'target_accepted_cases', 'rejected_cases',
        'provider_null_cases', 'failed_batch_still_returns_success_cases', 'validator_cases')}, indent=2))


if __name__ == '__main__':
    main()
