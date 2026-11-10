#!/usr/bin/env python3
"""Execute a desktop profile slice with supplied channel tables and M2.

This checks desktop arithmetic. It does not establish camera pixel order.
"""
from pathlib import Path
import argparse
import hashlib
import json
import random
import struct
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_SP, UC_ARM64_REG_X29, UC_ARM64_REG_X8, UC_ARM64_REG_PC

PIN = '7fe5cfaf4d35c9c4291cd502cd41835089c1a15755ace9bf3431d780cdba8424'
START, END = 0x1ca40c, 0x1cac80
SP, CONTEXT, PARAM = 0x10010000, 0x10020000, 0x11000000


def rounded(value, power):
    return (value + (1 << (power - 1)) - int(value < 0)) >> power


def matrix_pixel(matrix, rgb):
    result = [rounded(sum(rounded(matrix[3*r+c]*rgb[c],6) for c in range(3)),3) for r in range(3)]
    return tuple(max(0 if r == 0 else -4096, min(4095,value)) for r,value in enumerate(result))


def verify(sdk_path, output):
    blob = Path(sdk_path).read_bytes()
    assert hashlib.sha256(blob).hexdigest() == PIN
    u = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    offset = 32
    for _ in range(struct.unpack_from('<I', blob, 16)[0]):
        kind, size = struct.unpack_from('<II', blob, offset)
        if kind == 0x19:
            address, extent, pos, count = struct.unpack_from('<4Q', blob, offset+24)
            if extent:
                u.mem_map(address,(extent+4095)&~4095)
                u.mem_write(address,blob[pos:pos+count])
        offset += size
    u.mem_map(0x10000000,0x100000)
    u.mem_map(PARAM,0x10000)
    def put(a,v,fmt='Q'):u.mem_write(a,struct.pack('<'+fmt,v))
    def get(a,fmt='i'):return struct.unpack('<'+fmt,u.mem_read(a,struct.calcsize('<'+fmt)))[0]
    put(SP+0x408,CONTEXT)
    put(CONTEXT+0x270,PARAM)
    put(PARAM+0x4c,0,'h')
    u.reg_write(UC_ARM64_REG_SP,SP)
    u.reg_write(UC_ARM64_REG_X29,SP+0x900)
    tables = [[min(4095,x*x//(4096+1024*channel)) for x in range(4096)] for channel in range(3)]
    for channel, table in enumerate(tables):
        u.mem_write(PARAM+0x1d4+channel*0x2000,struct.pack('<4096H',*table))
    rng = random.Random(0x111201)
    witness = None
    for index in range(4096):
        coefficients = [rng.randrange(-2048,2048) for _ in range(9)]
        rgb = [rng.randrange(4096) for _ in range(3)]
        if index == 0:
            coefficients = [256,256,0,0,512,0,0,0,512]
            rgb = [400,1600,800]
        if index == 1:
            coefficients = [1]*9
            rgb = [256]*3
        u.mem_write(PARAM+0x61d4,struct.pack('<9h',*coefficients))
        for value,off in zip(rgb,(0x706,0x704,0x702)):put(SP+off,value,'H')
        u.reg_write(UC_ARM64_REG_X8,CONTEXT)
        u.emu_start(START,END,count=10000)
        assert u.reg_read(UC_ARM64_REG_PC) == END
        actual = tuple(get(SP+off) for off in (0x734,0x730,0x72c))
        lookup = [tables[channel][rgb[channel]] for channel in range(3)]
        expected = matrix_pixel(coefficients,lookup)
        assert actual == expected,(index,actual,expected)
        if index == 0:
            swapped = matrix_pixel(coefficients,rgb)
            swapped = tuple(tables[channel][max(0,value)] for channel,value in enumerate(swapped))
            assert swapped != expected
            witness = {'input_rgb':rgb,'m2_q9':coefficients,'tables_then_m2':actual,'m2_then_tables':swapped}
    result = {'passed':True,'cases':4096,'sdk_sha256':PIN,
              'source_span':{'start':hex(START),'end_exclusive':hex(END),
                             'sha256':hashlib.sha256(u.mem_read(START,END-START)).hexdigest()},
              'witness':witness,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'equation':'round_away(sum(round_away(Mij*xj/64))/8)',
              'limits':['Supplied stack locals, prepared tables, and coefficients. No instruction or helper replaced.',
                        'Desktop CProfGen slice only. No complete profile, hardware, or camera execution.']}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True, help='Pinned ARM64 debug SDK')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.sdk, args.output)
