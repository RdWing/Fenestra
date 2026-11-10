#!/usr/bin/env python3
"""Check pinned desktop CPXS preparation and YCbCr decoding.

The 1,024 decoder cases and three producer cases replace no helper. The 64
complete pixel runs use synthetic zero CPXS tables and model the C abs import.
These checks do not establish camera hardware order or recording color.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import random
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.arm64_const import (
    UC_ARM64_REG_SP, UC_ARM64_REG_PC, UC_ARM64_REG_LR,
    UC_ARM64_REG_X0, UC_ARM64_REG_CPACR_EL1,
)

PIN = '7fe5cfaf4d35c9c4291cd502cd41835089c1a15755ace9bf3431d780cdba8424'


def verify(sdk_path, output):
    blob = Path(sdk_path).read_bytes()
    if not hasattr(math, 'fma'):
        raise RuntimeError('This check requires Python 3.13 or newer for math.fma')
    assert hashlib.sha256(blob).hexdigest() == PIN
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    off = 32
    for _ in range(struct.unpack_from('<I', blob, 16)[0]):
        kind, size = struct.unpack_from('<II', blob, off)
        if kind == 0x19:
            address, extent, pos, count = struct.unpack_from('<4Q', blob, off + 24)
            if extent:
                u.mem_map(address, (extent + 4095) & ~4095)
                u.mem_write(address, blob[pos:pos + count])
        off += size
    u.mem_map(0x10000000, 0x100000)
    u.mem_map(0x11000000, 0x100000)
    u.reg_write(UC_ARM64_REG_CPACR_EL1, 3 << 20)

    def put(address, value, fmt='Q'):
        u.mem_write(address, struct.pack('<' + fmt, value))

    def get(address, fmt='Q'):
        return struct.unpack('<' + fmt, u.mem_read(address, struct.calcsize('<' + fmt)))[0]

    def span(address, size):
        return {'address':hex(address), 'bytes':size,
                'sha256':hashlib.sha256(u.mem_read(address,size)).hexdigest()}

    # Execute the full twelve-field copy and its original shared-pointer accessor.
    SP, TOP, TABLE, PARAM = 0x100e0000, 0x10010000, 0x11000000, 0x11080000
    put(SP+0x1200,TABLE)
    put(SP+0xc38,TOP)
    put(SP+0x1208,PARAM)
    table = bytes(range(36))
    u.mem_write(TABLE+0x1c504,table)
    producer_cases=[]
    for column in range(3):
        put(TOP+0x1514,column,'H')
        u.mem_write(PARAM+0x61e9,b'\xa5'*14)
        u.reg_write(UC_ARM64_REG_SP,SP)
        u.emu_start(0x3f83f4,0x3f8724,count=10000)
        assert u.reg_read(UC_ARM64_REG_PC)==0x3f8724
        actual=bytes(u.mem_read(PARAM+0x61ea,12))
        assert actual==table[column::3]
        assert get(PARAM+0x61e9,'B')==165 and get(PARAM+0x61f6,'B')==165
        producer_cases.append({'column':column,'control_bytes':list(actual)})

    # The complete pixel routine calls the platform C abs import. This hook models
    # that one import. It does not claim original instructions for that C library.
    imports=[]
    def abs_import(uc,address,size,data):
        value=uc.reg_read(UC_ARM64_REG_X0)&0xffffffff
        signed=value if value<0x80000000 else value-0x100000000
        uc.reg_write(UC_ARM64_REG_X0,abs(signed))
        uc.reg_write(UC_ARM64_REG_PC,uc.reg_read(UC_ARM64_REG_LR))
        imports.append(signed)
    u.hook_add(UC_HOOK_CODE,abs_import,begin=0x1adeac4,end=0x1adeac4)
    reads=[]
    def record_read(uc,access,address,size,value,data):
        reads.append((address-PARAM,size,uc.reg_read(UC_ARM64_REG_PC)))
    u.hook_add(UC_HOOK_MEM_READ,record_read,begin=PARAM+0x61d4,end=PARAM+0x61f5)
    u.mem_write(PARAM,bytes(0x40000))
    for channel in range(3):
        u.mem_write(PARAM+0x1d4+channel*0x2000,struct.pack('<4096H',*range(4096)))
    m2=(200,310,3,-65,-504,569,480,-484,4)
    u.mem_write(PARAM+0x61d4,struct.pack('<9h',*m2))
    WORK, RGB = 0x10020000,0x10010000
    put(WORK+8,17,'I')
    put(WORK+12,1,'I')
    put(WORK+0x38,PARAM)
    outputs=(0x10030000,0x10040000,0x10050000)
    for address,field in zip(outputs,(0x18,0x20,0x28)):
        put(WORK+field,address)
        u.mem_write(address,b'\xa5'*0x3000)
    patterns=[bytes(12),bytes((1,2,2,1,2,0,0,2,2,3,0,2)),
              bytes((1,2,2,1,2,0,0,3,3,3,0,2)),bytes([255]*12)]
    vectors=[(0,0,0),(1,1,1),(8,8,8),(16,16,16),
             (16,0,0),(0,16,0),(0,0,16),(16,16,0),
             (16,0,16),(0,16,16),(1,8,16),(16,8,1),
             (2,4,6),(6,4,2),(3,11,7),(11,3,7)]
    pixel_cases=[]
    for rgb in vectors:
        compared=[]
        for pattern in patterns:
            u.mem_write(RGB,struct.pack('<3i',*rgb))
            u.mem_write(PARAM+0x61ea,pattern)
            u.reg_write(UC_ARM64_REG_SP,0x100f0000)
            u.reg_write(UC_ARM64_REG_LR,0x100ffff0)
            for index,value in enumerate((0,RGB,RGB+4,RGB+8,WORK)):
                u.reg_write(UC_ARM64_REG_X0+index,value)
            before=len(reads)
            u.emu_start(0x1ca1d8,0x100ffff0,count=100000)
            assert u.reg_read(UC_ARM64_REG_PC)==0x100ffff0
            new=reads[before:]
            assert len(new)>=9
            assert all(address+size<=0x61ea for address,size,pc in new)
            position=rgb[0]*17*17+rgb[1]*17+rgb[2]
            actual=tuple(get(address+2*position,'H') for address in outputs)
            compared.append(actual)
        assert len(set(compared))==1
        pixel_cases.append({'rgb_grid':rgb,'output':compared[0]})
    inverse_ycc=list(struct.unpack('<9d',u.mem_read(0x1f7f590,72)))
    normalizer=get(0x1ba0e60,'d')
    assert normalizer==65535.0
    CONTEXT=0x100d0000
    put(SP+0x408,CONTEXT)
    put(SP+0x410,0x1f7f590)
    rng=random.Random(0x61f161f2)
    conversion_witnesses=[]
    # The complete routine ran with a later stop. Discard cached blocks before
    # applying the earlier stop at the end of this bounded arithmetic slice.
    u.ctl_remove_cache(0x1cfef0,0x1d0d4c)
    for index in range(1024):
        ycc=(rng.randrange(4096),rng.randrange(-2048,2048),rng.randrange(-2048,2048))
        for value,offset in zip(ycc,(0x540,0x548,0x70)):
            put(SP+offset,value,'i')
        u.reg_write(UC_ARM64_REG_SP,SP)
        u.emu_start(0x1cfef0,0x1cffd8,count=1000)
        assert u.reg_read(UC_ARM64_REG_PC)==0x1cffd8
        scaled=[(value*16)/normalizer for value in ycc]
        expected=[math.fma(inverse_ycc[3*r+2],scaled[2],
                  math.fma(inverse_ycc[3*r],scaled[0],inverse_ycc[3*r+1]*scaled[1]))
                  for r in range(3)]
        actual=[get(CONTEXT+offset,'d') for offset in (0x10,8,0)]
        assert struct.pack('<3d',*actual)==struct.pack('<3d',*expected),(index,actual,expected)
        if index<4:
            conversion_witnesses.append({'ycc':ycc,'rgb_before_clip':actual})
    result={'passed':True,'sdk_sha256':PIN,'producer_cases':producer_cases,
            'pixel_case_count':len(vectors)*len(patterns),'pixel_cases':pixel_cases,
            'control_patterns':[list(v) for v in patterns],
            'observed_parameter_reads':sorted(set(hex(a) for a,n,pc in reads)),
            'control_reads':0,'abs_import_calls':len(imports),
            'ycc_to_rgb_coefficients_f64':inverse_ycc,
            'ycc_to_rgb_cases':1024,'ycc_to_rgb_normalizer':normalizer,
            'ycc_to_rgb_witnesses':conversion_witnesses,
            'spans':[span(a,n) for a,n in ((0x3f83f4,0x330),(0x4031bc,0x18),
                (0x1ca1d8,0x6b74),(0x1f7f590,72),(0x1ba0e60,8),
                (0x1cfef0,0xe8),(0x4035f0,0x28),(0x4037a8,0x28))],
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'limits':['Synthetic parameter memory and zero CPXS tables; these are not complete native prepared profiles.',
                      'The complete pixel runs model the platform abs import in Python. The producer and YCbCr conversion checks replace no helper.',
                      'The tested complete desktop pixel runs do not read the twelve control bytes. This does not establish camera switch semantics.',
                      'No camera recording, pixel-domain, or hardware-order qualification.']}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('passed','pixel_case_count','control_reads','abs_import_calls','observed_parameter_reads','ycc_to_rgb_cases')},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='Pinned ARM64 debug SDK')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.sdk, args.output)
