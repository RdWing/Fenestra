"""Execute original C2.01 jobs with supplied Log3G10 producer pointers.

The compiled resident-source accessor executes on ARM. Python supplies the
six pointer substitutions at checked instruction boundaries. This checks the
producer contract, not installed hook preservation, scheduling or pixels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import itertools

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host.check_zr_color_transplant import Original, load_arm
from host.z63_log_profile import profile, producer_tables, generate_header, body_product
from host.color_transplant import PARAMETERS, SAMPLES, OFFSETS
from host.z63_log_view_profile import matrices as view_matrices, C6
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_W0, UC_ARM64_REG_PC, UC_ARM64_REG_LR


def check_view_selector(machine, panels):
    """Original selector with supplied table pointer and recording upload stubs."""
    u = machine.u
    original = bytes(u.mem_read(0x41876b70, 32))
    assert struct.unpack('<4Q', original) == (0xa02810bb0,0xa02810bc8,0xa02810cb8,0xa02810cd0)
    u.mem_write(0x180000, panels[0]+panels[1])
    u.mem_write(0x181000, struct.pack('<2Q', 0x180000, 0x180018)+original[16:])
    enabled, captures, changed = [False], [], [False]
    def observe(uc, pc, size, data):
        if pc == 0x402d8f7c:
            if enabled[0]:
                uc.reg_write(UC_ARM64_REG_X0+10, 0x181000)
                changed[0] = True
            return
        args = tuple(uc.reg_read(UC_ARM64_REG_X0+i) for i in range(4))
        if pc == 0x402b1050:
            captures.append((pc, args[:3], bytes(uc.mem_read(args[3]-2,24))))
        else:
            captures.append((pc, args, b''))
        uc.reg_write(UC_ARM64_REG_X0, 1 if pc == 0x402d9388 else 0)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
    hooks = [u.hook_add(UC_HOOK_CODE, observe, begin=pc, end=pc)
             for pc in (0x402d8f7c,0x402d9388,0x402b1050,0x402b14b8)]
    cases = custom = 0
    try:
        for a,b,d,flag,index,panel in itertools.product(range(3),range(3),range(2),range(2),range(2),range(2)):
            runs = []
            for selected in (False,True):
                enabled[0]=selected;captures.clear();changed[0]=False
                machine.put(0xa02fa4f9e,index,'B');machine.put(0xa02fa515c,flag,'B')
                machine.put(0xa028104d0,panel,'I')
                result=machine.run(0x402d8e54,a,b,d)
                runs.append((result,list(captures),changed[0]))
            stock,candidate=runs
            assert stock[0]==candidate[0]
            if candidate[2] and index==0:
                expected=[(pc,args,panels[panel] if pc==0x402b1050 else blob)
                          for pc,args,blob in stock[1]]
                assert candidate[1]==expected
                custom+=sum(pc==0x402b1050 for pc,_,_ in candidate[1])
            else:
                assert stock[1]==candidate[1]
            cases+=1
    finally:
        for hook in hooks:
            u.hook_del(hook)
    assert custom>0
    return {'selector_pairs':cases,'custom_matrix_uploads':custom,
            'uploaders':'supplied recording stubs; no physical display write'}


def verify(main, clang, linker, output):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    m = Original(main, 'z63')
    u = m.u
    # Read the actual initialized target record before deriving panel profiles.
    view_record = bytes(u.mem_read(0xa02810b68, 24))
    assert view_record[:2] == b'\x01\x01' and view_record[20:] == b'\x01\x00\x00\x00'
    c6 = struct.unpack_from('<9h', view_record, 2)
    assert c6 == C6
    panels = view_matrices(c6)
    view_checks = check_view_selector(m, panels)
    (out/'z63_log_assets.h').write_text(generate_header())
    source = ROOT/'src/platform/z63_c201/log_sources.c'
    subprocess.run([clang, '--target=aarch64-none-elf', '-O2', '-ffreestanding',
                    '-mgeneral-regs-only', '-mstrict-align', '-fno-stack-protector',
                    '-I', str(out), '-c', str(source), '-o', str(out/'sources.o')], check=True)
    subprocess.run([linker, '-m', 'aarch64elf', '-Ttext=0x46000000',
                    '--entry=fx_z63_log_source', str(out/'sources.o'),
                    '-o', str(out/'sources.elf')], check=True)
    entry = load_arm(m, (out/'sources.elf').read_bytes())
    pointers = [m.run(entry, part, 1) for part in range(5)]
    for pointer, blob in zip(pointers, producer_tables()):
        assert pointer % 16 == 0 and bytes(u.mem_read(pointer, len(blob))) == blob
    refusals = 0
    for selected in (0, 2, 0xffffffff):
        for part in range(7):
            assert m.run(entry, part, selected) == 0
            refusals += 1
    assert m.run(entry, 5, 1) == 0

    # (site, instruction, destination register, condition register, value, part, bias)
    sites = (
        (0x4111d12c, '0d00e0f2', 13, 12, 1, 0, 0x24),
        (0x4111dd20, '0900e0f2', 9, 10, 1, 1, 0x12),
        (0x4112729c, '0a00e0f2', 10, 8, 3, 2, 0),
        (0x411216a8, '2129029b', 1, 9, 1, 3, 0),
        (0x411258c8, '2129029b', 1, 9, 1, 3, 0),
    )
    for site, word, *_ in sites:
        assert bytes(u.mem_read(site, 4)) == bytes.fromhex(word)
    assert bytes(u.mem_read(0x41121614, 4)) == bytes.fromhex('e00313aa')
    active = [False]
    hits = {hex(site): 0 for site, *_ in sites}
    hits['0x41121614'] = 0

    def substitute(machine, pc, size, data):
        if not active[0]:
            return
        for site, word, dest, condition, value, part, bias in sites:
            if pc == site+4 and machine.reg_read(UC_ARM64_REG_W0+condition) == value:
                machine.reg_write(UC_ARM64_REG_X0+dest, pointers[part]-bias)
                hits[hex(site)] += 1
        if pc == 0x41121614:
            context = machine.reg_read(UC_ARM64_REG_X0+19)
            tone = m.get(context+0x98)
            if m.get(tone+0x31, 'B') == 1:
                m.put(context+0xb0, pointers[4])
                hits['0x41121614'] += 1

    # Restrict observers to the reviewed producer sites, not every instruction.
    for site, *_ in sites:
        u.hook_add(UC_HOOK_CODE, substitute, begin=site+4, end=site+4)
    u.hook_add(UC_HOOK_CODE, substitute, begin=0x41121614, end=0x41121614)
    u.mem_map(0x300000, 0x100000)
    j, c, f = 0x300000, 0x320000, 0x330000
    bodies = ((16384,0,0,0,16384,0,0,0,16384),
              (16000,384,0,0,16000,384,384,0,16000))
    cases = 0
    for file in (3, 4):
        for cls in (6, 7):
            for body in bodies:
                snapshots = []
                for selected in (False, True, False):
                    active[0] = selected
                    u.mem_write(j, bytes(0x11a20));u.mem_write(c, bytes(0xa60));u.mem_write(f, bytes(0x2cd9))
                    m.put(j+0x10, c);m.put(c+0xa58, f);m.put(c+0x10, cls, 'I');m.put(c+0x51, 1, 'B')
                    m.put(f, 1, 'I');m.put(f+0x3a4, file, 'I');m.put(j+0x154, 1, 'I');m.put(j+0x1c2, 256, 'H')
                    calibration = struct.pack('<H9h', 1, *body)
                    u.mem_write(f+0x5c6, calibration)
                    u.mem_write(0xa03d2a08c, bytes(5*0x2c0));m.put(0xa03d2ae4c, 0, 'I')
                    assert m.run(0x40e724ec, j) == 0 and m.get(c+0x54, 'B') == 1
                    m.run(0x40e7261c, j)
                    assert m.get(c+0x55, 'B') == 1
                    assert bytes(u.mem_read(f+0x5c6, 20)) == calibration
                    parameters = bytes(u.mem_read(j+0x1bd8, PARAMETERS))
                    samples = bytes(u.mem_read(j+0x287c, SAMPLES))
                    if selected:
                        assert struct.unpack_from('<9h', parameters, 0x1ea) == body_product(profile()['m1_base_q10'], body)
                        rgb = producer_tables()[2][:458]
                        assert all(samples[offset:offset+458] == rgb for offset in OFFSETS)
                        assert samples[0x16a2:0x186c] == producer_tables()[3]
                    snapshots.append((parameters, samples))
                    cases += 1
                assert snapshots[0] == snapshots[2]
                assert snapshots[0] != snapshots[1]
    result = {'passed': True, 'profile': profile(), 'original_job_cycles': cases,
              'stock_restorations': cases//3, 'accessor_refusals': refusals+1,
              'producer_substitutions': hits, 'firmware_sha256': hashlib.sha256(m.blob).hexdigest(),
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (source, Path(__file__), ROOT/'host/z63_log_profile.py', ROOT/'host/z63_log_view_profile.py')},
              'native_hook_installed': False, 'recording_qualified': False,
              'view_assist': {'stock_c6_record_hex': view_record.hex(),
                              'rear_record_hex': panels[0].hex(), 'evf_record_hex': panels[1].hex(),
                              'original_selector': view_checks,
                              'panel_appearance_tested': False, 'tone_curves_qualified': False},
              'scope': 'Original ordinary-route jobs; supplied source-pointer substitutions, synthetic frames and body matrices. No physical or pixel-color claim.'}
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('main', 'clang', 'linker', 'output'):
        parser.add_argument('--'+key, required=True)
    print(json.dumps(verify(**vars(parser.parse_args())), indent=2))
