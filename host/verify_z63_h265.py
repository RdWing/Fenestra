"""Replay the linked C2.01 H.265 selector and service with supplied inputs."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
import unicorn.arm64_const as arm


BASE = 0x40160000
SELECTOR = 0x402fbe64
TAIL = 0x402fbfcc
COPY = 0x4163b5c0
PARAMETERS = 0x402ffe60
PARAMETER_BYTES = 0x220
ROWS = 0x42ac02fc
ROW_BYTES = 36
ROW_COUNT = 61
PERCENT = (100, 60, 45, 30, 20)


def verify(application, build):
    original = Path(application).read_bytes()
    build = Path(build)
    image = (build / 'probe.eg.bin').read_bytes()
    receipt = json.loads((build / 'probe.json').read_text())
    if (hashlib.sha256(original).hexdigest() != receipt['application_sha256'] or
            hashlib.sha256(image).hexdigest() != receipt['candidate_sha256']):
        raise ValueError('H.265 check input differs from the build receipt')
    symbols = receipt['symbols']
    layout = struct.unpack_from('<7I', image, symbols['fx_z63_h265_layout'] - BASE)
    if layout[:2] != (0x46584835, 1):
        raise ValueError('H.265 observation layout differs')
    cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu.mem_map(BASE, (len(image)+4095) & ~4095)
    cpu.mem_write(BASE, image)
    ram = 0x10000000
    cpu.mem_map(ram, 0x40000)
    cpu.reg_write(arm.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    state, owner, cookie, request, reply, mode, out, stop = [ram+4096*i for i in range(8)]
    regs = [getattr(arm, 'UC_ARM64_REG_X'+str(i)) for i in range(8)]
    cpu.mem_map(0xa048bb000, 4096)
    cpu.mem_map(0xa03324000, 4096)
    cpu.mem_map(0xa03d42000, 4096)
    tier_state = state + layout[2]
    selected_source = None
    reading_selector = False
    file_type = 2

    def put(at, value):
        cpu.mem_write(at, struct.pack('<I', value))

    def effective():
        return struct.unpack('<I', cpu.mem_read(tier_state+layout[4], 4))[0]

    def call(address, *args):
        for i, register in enumerate(regs):
            cpu.reg_write(register, args[i] if i < len(args) else 0)
        cpu.reg_write(arm.UC_ARM64_REG_SP, ram+0x3f000)
        cpu.reg_write(arm.UC_ARM64_REG_LR, stop)
        cpu.emu_start(address, stop, count=20000)
        if cpu.reg_read(arm.UC_ARM64_REG_PC) != stop:
            raise ValueError('H.265 instruction budget exhausted')
        return cpu.reg_read(regs[0])

    def substitute(mu, pc, size, context):
        nonlocal selected_source
        if pc == COPY:
            if not reading_selector:
                return
            dst, src, length = (mu.reg_read(reg) for reg in regs[:3])
            if length != ROW_BYTES or not ROWS <= src < ROWS+ROW_BYTES*ROW_COUNT:
                raise ValueError('selector copy outside original rows')
            selected_source = src
            mu.mem_write(dst, bytes(mu.mem_read(src, length)))
            result = dst
        elif pc == symbols['fx_z63_menu_video']:
            result = state
        elif pc == 0x403ffcd0:
            result = file_type
        else:
            result = 1
        mu.reg_write(regs[0], result)
        mu.reg_write(arm.UC_ARM64_REG_PC, mu.reg_read(arm.UC_ARM64_REG_LR))

    for address in (COPY, symbols['fx_z63_menu_video'], 0x403ffcd0, 0x40d32f74, 0x40d32f60):
        cpu.hook_add(UC_HOOK_CODE, substitute, begin=address, end=address)

    def selector(inputs):
        nonlocal reading_selector
        cpu.mem_write(mode, struct.pack('<4I', *inputs))
        cpu.mem_write(out, b'\xa5'*64)
        reading_selector = True
        try:
            assert call(SELECTOR, mode, out+8) == out+8
        finally:
            reading_selector = False
        return bytes(cpu.mem_read(out, 64))

    def parameters(flag, extra):
        destination = ram + 0x9010
        cpu.mem_write(destination-16, b'\xa5'*(PARAMETER_BYTES+32))
        call(PARAMETERS, out+8, flag, extra, destination)
        assert bytes(cpu.mem_read(destination-16, 16)) == b'\xa5'*16
        assert bytes(cpu.mem_read(destination+PARAMETER_BYTES, 16)) == b'\xa5'*16
        return bytes(cpu.mem_read(destination, PARAMETER_BYTES))

    def resource(op, selection=None):
        cpu.mem_write(request, bytes(816))
        if selection is not None:
            cpu.mem_write(request+12, struct.pack('<I', 16))
            cpu.mem_write(request+32, struct.pack('<Q', 2))
            cpu.mem_write(request+48, struct.pack('<4I', 1, 16, 4, selection))
        return call(symbols['fx_z63_h265_resource'], 0, op, 0, owner, 7, cookie, request, reply)

    cpu.mem_write(TAIL, original[TAIL-BASE:TAIL-BASE+4])
    samples = {}
    for inputs in itertools.product(range(2), range(2), range(4), range(13)):
        result = selector(inputs)
        index = (selected_source-ROWS)//ROW_BYTES
        samples.setdefault(index, (inputs, result))
    assert set(samples) == set(range(ROW_COUNT))
    cpu.mem_write(TAIL, image[TAIL-BASE:TAIL-BASE+4])
    cpu.ctl_remove_cache(SELECTOR, TAIL+4)

    put(state+layout[3], 1)
    put(tier_state+layout[5], 3)
    assert resource(1) == 0
    for file_type in (0, 1, 4, 5, 6, 7):
        assert resource(3, 1) == 2 and effective() == 0
    file_type = 3
    put(0xa03d42100, 1)
    assert resource(3, 1) == 0 and effective() == 0
    put(0xa03d42100, 2)
    assert resource(3, 1) == 0 and effective() == 1
    eligible_rows = 0
    stock_parameters = {}
    parameter_cases = 0
    uhd10_targets = []
    uhd10_nominal = []
    for tier, percent in enumerate(PERCENT):
        assert resource(3, tier) == 0 and effective() == tier
        eligible_rows = 0
        for index, (inputs, stock) in samples.items():
            expected = bytearray(stock)
            codec, dimensions = struct.unpack_from('<2I', stock, 8)
            eligible = codec == 1 and dimensions >> 16 in (1920, 3840, 5376)
            if eligible:
                eligible_rows += 1
                nominal, = struct.unpack_from('<I', stock, 36)
                struct.pack_into('<I', expected, 36, nominal*percent//100)
            if selector(inputs) != expected or selected_source != ROWS+index*ROW_BYTES:
                raise ValueError(f'H.265 selector mismatch for tier {tier}, row {index}')
            if not eligible:
                continue
            rate, = struct.unpack_from('<I', expected, 36)
            for flag, extra in itertools.product((0, 1), (0, ram+0xb000)):
                block = parameters(flag, extra)
                assert bytes(cpu.mem_read(out, 64)) == expected
                target, = struct.unpack_from('<I', block, 0x18)
                assert target == rate//1200
                key = index, flag, extra
                if tier == 0:
                    stock_parameters[key] = block
                stock_block = stock_parameters[key]
                assert block[:0x18] == stock_block[:0x18]
                assert block[0x1c:0x24] == stock_block[0x1c:0x24]
                assert block[0x28:] == stock_block[0x28:]
                if index == 49 and flag == 0 and extra == 0:
                    uhd10_targets.append(target)
                    uhd10_nominal.append(rate)
                parameter_cases += 1
    assert eligible_rows == 42
    put(tier_state+layout[6], 1)
    assert resource(2) == 5 and effective() == 4
    put(tier_state+layout[6], 0)
    assert resource(2) == 0 and effective() == 0
    return dict(passed=True, candidate_sha256=receipt['candidate_sha256'],
                selector_cases=ROW_COUNT*len(PERCENT), eligible_rows=eligible_rows,
                preserved_rows=ROW_COUNT-eligible_rows, wrong_mode_refusals=6,
                encoder_parameter_cases=parameter_cases,
                uhd_2997_10bit_parameter_words=uhd10_targets,
                uhd_2997_10bit_nominal_bps=uhd10_nominal,
                idle_publication=True, deferred_stock_retirement=True,
                qualification='Linked selector and service with substituted copy leaf, mutex, context and setting reads.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.application, args.build), indent=2))
