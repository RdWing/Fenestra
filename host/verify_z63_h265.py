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
    layout = struct.unpack_from('<9I', image, symbols['fx_z63_h265_layout'] - BASE)
    if layout[:2] != (0x46584835, 2):
        raise ValueError('H.265 observation layout differs')
    cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu.mem_map(BASE, (len(image)+4095) & ~4095)
    cpu.mem_write(BASE, image)
    ram = 0x10000000
    cpu.mem_map(ram, 0x40000)
    cpu.reg_write(arm.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    state, owner, cookie, request, reply, mode, out, stop = [ram+4096*i for i in range(8)]
    # The guard now requires an owned published header. Keep that admission
    # fixture separate from the substituted context getter, but use the real
    # target offset so both identify the same controller storage.
    video_layout = struct.unpack_from('<9I', image, symbols['fx_z63_video_layout']-BASE)
    root = 0xa01000000
    cpu.mem_map(root,0x10000)
    cpu.mem_map(0xa02912000,4096)
    cpu.mem_write(0xa02912e60,struct.pack('<Q',root))
    cpu.mem_write(root+64,struct.pack('<II',0x465a634d,1))
    if receipt.get('activation'):
        # Supplied active RAM-text fixture. The flash artifact must still
        # contain the original words; installation itself has separate tests.
        cpu.mem_map(0xa17200000,0x30000)
        cpu.mem_write(root+76,struct.pack('<I',1))
        count=struct.unpack_from('<I',image,symbols['fx_z63_activation_count']-BASE)[0]
        for i in range(count):
            site,old,new=struct.unpack_from('<III',image,symbols['fx_z63_activation_words']-BASE+i*12)
            if struct.unpack_from('<I',image,site-BASE)[0]!=old:raise ValueError('feature hook present in flash')
            cpu.mem_write(site,struct.pack('<I',new))
    state = root+video_layout[2]
    regs = [getattr(arm, 'UC_ARM64_REG_X'+str(i)) for i in range(8)]
    cpu.mem_map(0xa048bb000, 4096)
    cpu.mem_map(0xa03324000, 4096)
    cpu.mem_map(0xa03d42000, 4096)
    cpu.mem_map(0xa03f0e000, 4096)
    tier_state = state + layout[2]
    selected_source = None
    reading_selector = False
    file_type = 2
    save_behavior = "success"
    metadata_result = 1
    metadata_calls = 0

    def put(at, value):
        cpu.mem_write(at, struct.pack('<I', value))

    def effective():
        return struct.unpack('<I', cpu.mem_read(tier_state+layout[4], 4))[0]

    def call(address, *args):
        for i, register in enumerate(regs):
            cpu.reg_write(register, args[i] if i < len(args) else 0)
        cpu.reg_write(arm.UC_ARM64_REG_SP, ram+0x3f000)
        cpu.reg_write(arm.UC_ARM64_REG_LR, stop)
        cpu.emu_start(address, stop, count=4000000)
        if cpu.reg_read(arm.UC_ARM64_REG_PC) != stop:
            raise ValueError('H.265 instruction budget exhausted')
        return cpu.reg_read(regs[0])

    def substitute(mu, pc, size, context):
        nonlocal selected_source, metadata_calls
        if pc == COPY:
            if not reading_selector:
                return
            dst, src, length = (mu.reg_read(reg) for reg in regs[:3])
            if length != ROW_BYTES or not ROWS <= src < ROWS+ROW_BYTES*ROW_COUNT:
                raise ValueError('selector copy outside original rows')
            selected_source = src
            mu.mem_write(dst, bytes(mu.mem_read(src, length)))
            result = dst
        elif pc == 0x41003bc0:
            if save_behavior == 'suppressed':
                mu.reg_write(arm.UC_ARM64_REG_PC, mu.reg_read(arm.UC_ARM64_REG_LR))
                return
            mu.reg_write(regs[0], 0)
            mu.reg_write(arm.UC_ARM64_REG_PC, symbols['fx_z63_h265_save_result'])
            return
        elif pc == 0x41003538:
            if save_behavior == 'reset':
                put(0xa03f0eef4, 1)
            elif save_behavior == 'recall-prores':
                put(0xa03f0eef4, 0x56a00301)
            elif save_behavior == 'foreign':
                put(0xa03f0eef4, 0x12345601)
            elif save_behavior == 'low-byte':
                current, = struct.unpack('<I', mu.mem_read(0xa03f0eef4, 4))
                put(0xa03f0eef4, current ^ 1)
            result = 0 if save_behavior in ('failed', 'reset', 'foreign', 'recall-prores') else 1
        elif pc == symbols['fx_z63_video_h265_metadata_original']:
            metadata_calls += 1
            result = metadata_result
        elif pc == symbols['fx_z63_menu_video']:
            result = state
        elif pc == 0x403ffcd0:
            result = file_type
        else:
            result = 1
        mu.reg_write(regs[0], result)
        mu.reg_write(arm.UC_ARM64_REG_PC, mu.reg_read(arm.UC_ARM64_REG_LR))

    for address in (COPY, symbols['fx_z63_menu_video'], 0x403ffcd0, 0x40d32f74, 0x40d32f60, 0x41003bc0, 0x41003538, symbols['fx_z63_video_h265_metadata_original']):
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

    active_tail=bytes(cpu.mem_read(TAIL,4))
    cpu.mem_write(TAIL, original[TAIL-BASE:TAIL-BASE+4])
    samples = {}
    for inputs in itertools.product(range(2), range(2), range(4), range(13)):
        result = selector(inputs)
        index = (selected_source-ROWS)//ROW_BYTES
        samples.setdefault(index, (inputs, result))
    assert set(samples) == set(range(ROW_COUNT))
    cpu.mem_write(TAIL, active_tail)
    cpu.ctl_remove_cache(SELECTOR, TAIL+4)

    put(owner+layout[7], 1)
    put(state+layout[3], 1)
    put(tier_state+layout[5], 3)
    assert resource(1) == 0
    for file_type in (0, 1, 4, 5, 6, 7):
        assert resource(3, 1) == 2 and effective() == 0
    file_type = 3
    put(0xa03d42100, 1)
    assert resource(3, 1) == 5 and effective() == 0
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
    # Independently fence each native worker and wrapper counter. An unchanged
    # effective tier alone must not hide a premature persisted-word write.
    admission_cases = 0
    for address, busy in ((0xa048bb044, 2), (0xa03324ce0, 1),
                          (0xa03324dc8, 1), (0xa03d42100, 3),
                          (0xa03d42108, 12),
                          (tier_state+layout[6], 1),
                          (tier_state+layout[6]+4, 1)):
        previous = bytes(cpu.mem_read(address, 4))
        put(address, busy)
        for choice in range(5):
            persisted = bytes(cpu.mem_read(0xa03f0eef4, 4))
            assert resource(3, choice) == 5 and effective() == 4
            assert bytes(cpu.mem_read(0xa03f0eef4, 4)) == persisted
            admission_cases += 1
        cpu.mem_write(address, previous)
    for save_behavior in ('failed', 'suppressed'):
        prior = bytes(cpu.mem_read(0xa03f0eef4, 4))
        assert resource(3, 2) == 2 and effective() == 4
        assert bytes(cpu.mem_read(0xa03f0eef4, 4)) == prior
    prior, = struct.unpack('<I', cpu.mem_read(0xa03f0eef4, 4))
    save_behavior = 'low-byte'
    assert resource(3, 3) == 0 and effective() == 3
    current, = struct.unpack('<I', cpu.mem_read(0xa03f0eef4, 4))
    assert current & 255 == (prior & 255) ^ 1
    save_behavior = 'reset'
    assert resource(3, 2) == 2 and effective() == 0
    assert bytes(cpu.mem_read(0xa03f0eef4, 4)) == struct.pack('<I', 1)
    save_behavior = 'success'
    assert resource(3, 4) == 0 and effective() == 4
    put(tier_state+layout[6], 1)
    assert resource(2) == 5 and effective() == 4
    put(tier_state+layout[6], 0)
    assert resource(2) == 0 and effective() == 0
    assert resource(1) == 0 and effective() == 4
    metadata_cases = 0
    for tier, kind, alternate, quality, metadata_result in itertools.product(range(5), range(8), range(2), range(4), range(2)):
        put(tier_state+layout[4], tier)
        source = bytearray(256);struct.pack_into('<I', source, 0x20, kind);source[0xec] = alternate
        destination = bytearray(b'\xa5'*256);struct.pack_into('<I', destination, 0xa8, quality)
        cpu.mem_write(mode, bytes(source));cpu.mem_write(out, bytes(destination))
        expected = bytearray(destination)
        if metadata_result == 1 and kind in (2, 3) and not alternate and quality == 1 and tier:
            struct.pack_into('<I', expected, 0xa8, 2)
        before_calls = metadata_calls
        assert call(symbols['fx_z63_h265_metadata'], mode, out) == metadata_result
        assert metadata_calls == before_calls+1
        assert bytes(cpu.mem_read(mode, 256)) == source and bytes(cpu.mem_read(out, 256)) == expected
        metadata_cases += 1
    put(tier_state+layout[4], 4)
    video_layout = struct.unpack_from('<9I', image, symbols['fx_z63_video_layout']-BASE)
    prores_state = state+video_layout[3]
    prores_owner=ram+0xc000
    put(prores_owner+layout[7],1)
    put(prores_state+video_layout[6], 3)
    def prores(op, choice=None):
        cpu.mem_write(request, bytes(816))
        if choice is not None:
            cpu.mem_write(request+12, struct.pack('<I',16))
            cpu.mem_write(request+32, struct.pack('<Q',2))
            cpu.mem_write(request+48, struct.pack('<4I',1,16,1,choice))
        return call(symbols['fx_z63_video_resource'],0,op,0,prores_owner,8,cookie+16,request,reply)
    def prores_effective():
        return struct.unpack('<I',cpu.mem_read(prores_state+video_layout[4],4))[0]
    assert prores(1)==0
    put(state+layout[8],1)
    assert prores(3,2)==5
    assert prores(2)==5
    cpu.mem_write(request,bytes(816))
    cpu.mem_write(request+12,struct.pack('<I',16))
    cpu.mem_write(request+32,struct.pack('<Q',2))
    cpu.mem_write(request+48,struct.pack('<4I',1,16,3,1))
    cpu.mem_write(cookie+32,struct.pack('<Q',9))
    assert call(symbols['fx_z63_raw_resource'],0,3,0,owner,9,cookie+32,request,reply)==5
    put(state+layout[8],0)
    for choice in range(5):
        before=struct.unpack('<I',cpu.mem_read(0xa03f0eef4,4))[0]
        assert prores(3,choice)==0 and prores_effective()==choice
        after=struct.unpack('<I',cpu.mem_read(0xa03f0eef4,4))[0]
        assert (before&0xfffffcff)==(after&0x00fffcff)|(before&0xff000000)
        assert ((after>>8)&3)==max(0,choice-1)
        assert prores(2)==0 and prores_effective()==0
        assert prores(1)==0 and prores_effective()==(choice if choice>1 else 0)
    for save_behavior in ('failed','suppressed'):
        before=bytes(cpu.mem_read(0xa03f0eef4,4))
        assert prores(3,2)==2 and prores_effective()==4
        assert bytes(cpu.mem_read(0xa03f0eef4,4))==before
    save_behavior='success'
    assert prores(3,1)==0 and prores_effective()==1
    for save_behavior in ('failed','suppressed'):
        before=bytes(cpu.mem_read(0xa03f0eef4,4))
        assert prores(3,2)==2 and prores_effective()==1
        assert bytes(cpu.mem_read(0xa03f0eef4,4))==before
    save_behavior='success'
    assert prores(3,3)==0 and prores_effective()==3
    save_behavior='reset'
    assert resource(3,2)==2 and effective()==0 and prores_effective()==0
    save_behavior='success'
    assert resource(3,4)==0 and effective()==4
    assert prores(3,1)==0 and prores_effective()==1
    save_behavior='reset'
    assert prores(3,2)==2 and prores_effective()==0 and effective()==0
    assert bytes(cpu.mem_read(0xa03f0eef4,4))==struct.pack('<I',1)
    save_behavior='success'
    assert prores(2)==0
    assert resource(3,4)==0 and effective()==4
    assert prores(1)==0
    assert prores(3,3)==0 and prores_effective()==3
    put(prores_owner+layout[7],0)
    save_behavior='reset'
    assert resource(3,2)==2 and effective()==0 and prores_effective()==3
    save_behavior='success'
    assert prores(2)==0 and prores_effective()==0
    put(prores_owner+layout[7],1)
    assert resource(3,4)==0 and effective()==4
    assert prores(1)==0 and prores_effective()==0
    file_type=6
    cpu.mem_write(request,bytes(816))
    cpu.mem_write(request+12,struct.pack('<I',16))
    cpu.mem_write(request+32,struct.pack('<Q',2))
    cpu.mem_write(request+48,struct.pack('<4I',1,16,3,1))
    cpu.mem_write(cookie+32,struct.pack('<Q',9))
    assert call(symbols['fx_z63_raw_resource'],0,3,0,owner,9,cookie+32,request,reply)==0
    save_behavior='recall-prores'
    assert resource(3,0)==2 and effective()==0 and prores_effective()==0
    assert struct.unpack('<I',cpu.mem_read(prores_state+video_layout[8],4))[0]==1
    assert bytes(cpu.mem_read(0xa03f0eef4,4))==struct.pack('<I',0x56a00301)
    file_type=3;save_behavior='success'
    assert resource(3,4)==0 and effective()==4
    save_behavior = 'foreign'
    assert resource(3, 2) == 2 and effective() == 4
    assert bytes(cpu.mem_read(0xa03f0eef4, 4)) == struct.pack('<I', 0x12345601)
    return dict(passed=True, candidate_sha256=receipt['candidate_sha256'],
                selector_cases=ROW_COUNT*len(PERCENT), eligible_rows=eligible_rows,
                preserved_rows=ROW_COUNT-eligible_rows, wrong_mode_refusals=6,
                encoder_parameter_cases=parameter_cases,
                independent_busy_fence_cases=admission_cases,
                prores_persistence_choices=5, prores_failed_saves_preserved=True, nonrunning_peer_preserved=True, conflicting_recall_fails_closed=True,
                metadata_wrapper_cases=metadata_cases, metadata_original_called_once=True,
                uhd_2997_10bit_parameter_words=uhd10_targets,
                uhd_2997_10bit_nominal_bps=uhd10_nominal,
                idle_publication=True, deferred_stock_retirement=True,
                failed_and_suppressed_saves_rollback=True, reset_wins=True,
                ordinary_byte_preserved=True, foreign_word_preserved=True, saved_tier_reload=True,
                qualification='Linked selector and service with substituted copy leaf, mutex, context and setting reads.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.application, args.build), indent=2))
