"""Check the complete RWG candidate against original C2.01 buffer writers.

Uses supplied memory and synthetic coefficients. No camera, native recording
hook, decoder, fitted color acceptance or hardware pixel execution is implied.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from host.check_zr_color_transplant import Original, load_arm
from host.color_transplant import library, PARAMETERS, SAMPLES, SIZE, OFFSETS


def verify(main, clang, linker, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    machine = Original(main, 'z63')
    with tempfile.TemporaryDirectory() as temporary:
        objects = []
        sources = ('src/platform/z63_c201/color_transplant.c', 'src/memory.c')
        for i, source in enumerate(sources):
            obj = Path(temporary) / f'{i}.o'
            subprocess.run([clang, '--target=aarch64-none-elf', '-O2', '-ffreestanding',
                            '-fno-builtin', '-mgeneral-regs-only', '-mstrict-align',
                            '-fno-stack-protector', '-DFX_FREESTANDING=1', '-I', str(ROOT/'include'),
                            '-c', str(ROOT/source), '-o', str(obj)], check=True)
            objects.append(str(obj))
        elf = output/'rwg-candidate.elf'
        subprocess.run([linker, '-m', 'aarch64elf', '-Ttext=0x46000000',
                        '--entry=fx_z63_color_rwg_candidate', *objects, '-o', str(elf)], check=True)
        entry = load_arm(machine, elf.read_bytes())
        lib, _ = library(temporary)
        fn = lib.fx_z63_color_rwg_candidate
        fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
                       ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
                       ctypes.c_void_p, ctypes.c_size_t]
        fn.restype = ctypes.c_int
        p = bytearray([0x5a]*PARAMETERS)
        p[0x1e8:0x1ea] = bytes(2)
        p[0x263] = p[0x264] = 2
        s = bytes([0x69]*SAMPLES)
        matrices = [(1024,0,0,0,1024,0,0,0,1024),
                    (900,200,-76,-20,1060,-16,10,40,974),
                    (-4096,4095,0,0,1024,0,0,0,1024)]
        words_checked = 0
        for coefficients in matrices:
            for ceiling in (24693, 32736, 32763):
                curve = tuple(min(ceiling, 3000+i*140) for i in range(229))
                buffer = (ctypes.c_ubyte*SIZE)()
                m = (ctypes.c_int16*9)(*coefficients)
                lut = (ctypes.c_uint16*229)(*curve)
                assert fn(buffer, bytes(p), PARAMETERS, s, SAMPLES, m, 9, lut, 229) == 1
                expected = bytes(buffer)
                u = machine.u
                u.mem_write(0x180000, bytes(p));u.mem_write(0x182000, s)
                u.mem_write(0x186000, struct.pack('<9h', *coefficients))
                u.mem_write(0x187000, struct.pack('<229H', *curve))
                u.mem_write(0x190000, b'\xa5'*(SIZE+32))
                # Argument nine lives on the original AArch64 entry stack.
                machine.put(0x1fe000, 229)
                assert machine.run(entry, 0x190010, 0x180000, PARAMETERS,
                                   0x182000, SAMPLES, 0x186000, 9, 0x187000) == 1
                assert bytes(u.mem_read(0x190010, SIZE)) == expected
                assert bytes(u.mem_read(0x190000, 16)) == b'\xa5'*16
                assert bytes(u.mem_read(0x190010+SIZE, 16)) == b'\xa5'*16
                source = 0x190010+PARAMETERS
                machine.put(0x120008, 0x130000)
                u.mem_write(0x1a0000, bytes(0x600))
                machine.run(0x40e625cc, source, 0x1a0000)
                for bank, register in enumerate((0x4210,0x43dc,0x45b0,0x477c,0x4950,0x4b1c)):
                    pointer = machine.get(0x1a0458+8*bank)
                    assert pointer == source+OFFSETS[bank]
                    machine.run(0x40c11bf8, 0x120000, bank%2, bank//2, pointer)
                    words = [curve[i] | curve[i+1]<<16 for i in range(0,228,2)]+[curve[-1]]
                    assert list(struct.unpack('<115I',u.mem_read(0x130000+register,460))) == words
                    words_checked += 115
                machine.run(0x40c11cac, 0x120000, source+0x16a2)
                nlg = [(v+4)//8 for v in curve]
                words = [nlg[i] | nlg[i+1]<<16 for i in range(0,228,2)]+[nlg[-1]]
                assert list(struct.unpack('<115I',u.mem_read(0x134cf0,460))) == words
                words_checked += 115
                for driver, offset, mask, values in (
                    (0x40c10d94, 0x15e0, 8191, coefficients),
                    (0x40c11004, 0x1664, 4095, (109,366,37,-59,-197,256,256,-233,-23))):
                    pointer = 0x190010+(0x1e8 if mask==8191 else 0x248)
                    machine.run(driver, 0x120000, pointer)
                    words = [(values[i]&mask) | (values[i+1]&mask)<<16 for i in range(0,8,2)]+[values[8]&mask]
                    assert list(struct.unpack('<5I',u.mem_read(0x130000+offset,20))) == words
                    words_checked += 5
                for field, (driver,value) in enumerate(zip(
                        (0x40c11304,0x40c11354,0x40c113a8,0x40c113fc,0x40c11450,0x40c114a4),
                        (253,-28,-19,252,26,50))):
                    for bank in range(2):
                        offset = 64*(2*field+bank)
                        machine.run(driver, 0x120000, bank, source+offset)
                        word = (value&1023) | (value&1023)<<16
                        assert list(struct.unpack('<16I',u.mem_read(0x133000+offset,64))) == [word]*16
                        words_checked += 16
        result = dict(passed=True, original_writer_words=words_checked, arm_host_cases=9,
                      firmware_sha256=hashlib.sha256(machine.blob).hexdigest(),
                      elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
                      sources={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                               for name in (*sources,'src/platform/z63_c201/color_transplant.h',
                                            'host/check_z63_rwg_candidate.py')},
                      compiler=subprocess.check_output([clang,'--version'],text=True).strip(),
                      linker=subprocess.check_output([linker,'--version'],text=True).strip(),
                      live_hook_installed=False, color_basis_qualified=False,
                      scope='Synthetic host/ARM candidate parity and original buffer writers; no pixel or recording qualification')
        (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('main','clang','linker','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(args.main,args.clang,args.linker,args.output),indent=2))
