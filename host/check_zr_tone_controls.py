#!/usr/bin/env python3
"""Check ZR CPXS recipes and their original C2.01 transport."""
from pathlib import Path
import argparse
import hashlib
import json
import struct

try:
    from .check_zr_lut_source import Original, loader_sha256, write_result
except ImportError:
    from check_zr_lut_source import Original, loader_sha256, write_result

ROWS = ((1,2,2,1,2,0,0,2,2,3,0,2), (1,2,2,1,2,0,0,2,2,3,0,2),
        (1,3,2,1,3,0,0,2,3,3,0,2), (1,2,2,1,2,0,0,3,3,3,0,2))


def packed(row):
    return (sum((v&3)<<(4*i) for i,v in enumerate(row[:8])),
            sum((row[i+8]&m)<<(4*i) for i,m in enumerate((3,7,3,7))))


def verify(zr_path, z63_path, output):
    zr = Original(zr_path,'zr')
    c = Original(z63_path,'z63')
    assert bytes(zr.u.mem_read(0xa02a1ff21,48)) == bytes(v for row in ROWS for v in row)
    cases = []
    for tone in (-2147483648,-1,0,1,2,3,4,2147483647):
        row = ROWS[max(0,min(3,tone))]
        for flag0,flag1,weight,level in ((0,0,0,0),(0,0,256,0),(1,0,100,5),(0,1,100,5)):
            zr.u.mem_write(0x140000,bytes(0x200))
            zr.u.mem_write(0x150000,bytes(0x200))
            zr.u.mem_write(0x160000,b'\xa5'*0x100)
            zr.put(0x140040,0x150000)
            zr.put(0x1400a0,0x160000)
            zr.put(0x1500b8,tone,'i')
            zr.put(0x150110,flag0,'B')
            zr.put(0x150111,flag1,'B')
            zr.put(0x15012a,weight,'H')
            zr.put(0x150008,level,'B')
            zr.run(0x41312620,0x140000)
            actual = bytes(zr.u.mem_read(0x160084,12))
            assert actual == bytes(row)
            alpha = 2048 if flag0 else int((20480-2048*level)/10) if flag1 else weight*8
            assert zr.get(0x160082,'H') == (alpha & 65535)
            assert bytes(zr.u.mem_read(0x160000,0x82)) == b'\xa5'*0x82
            assert bytes(zr.u.mem_read(0x160090,0x70)) == b'\xa5'*0x70
            # Keep source and derived pointers distinct, as in the adapter.
            c.u.mem_write(0x140000,bytes(0x500))
            c.u.mem_write(0x150000,bytes(0x600))
            c.u.mem_write(0x160000,bytes(0x500))
            c.put(0x140400,0x160000)
            c.u.mem_write(0x16025c,actual)
            c.run(0x40e60b5c,0x140000,0x150000)
            ptr = c.get(0x150350)
            assert ptr == 0x16025c
            c.put(0x170008,0x180000)
            c.u.mem_write(0x181670,b'\xa5'*32)
            c.run(0x40c11068,0x170000,ptr)
            registers = struct.unpack('<2I',c.u.mem_read(0x18167c,8))
            assert registers == packed(row)
            assert bytes(c.u.mem_read(0x181670,12)) == b'\xa5'*12
            assert bytes(c.u.mem_read(0x181684,12)) == b'\xa5'*12
            cases.append({'tone':tone,'flags':[flag0,flag1],'weight':weight,'level':level,
                          'alpha':alpha,'row':row,'registers':[hex(v) for v in registers]})
    result = {'passed':True,'cases':cases,'producer_cases':len(cases),'builder_and_driver_cases':len(cases),
              'firmware_sha256':{'zr':hashlib.sha256(zr.blob).hexdigest(),
                                 'z63':hashlib.sha256(c.blob).hexdigest()},
              'loader_source_sha256':loader_sha256(),
              'recipe_rows':ROWS,'tone1_registers':[hex(v)for v in packed(ROWS[1])],
              'tone3_registers':[hex(v)for v in packed(ROWS[3])],
              'regions':{'zr':[zr.region(0x41312620,0xa0)],
                         'z63':[c.region(0x40c11068,0x90),c.region(0x40e60b5c,0x460)]},
              'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'limits':['Original producer, complete dynamic builder, and original writer with synthetic memory.',
                        'Register slots are RAM in this test. CPXS switch semantics and camera pixel order remain unknown.']}
    write_result(output, result)
    print(json.dumps({k:result[k] for k in ('passed','producer_cases','builder_and_driver_cases','tone1_registers','tone3_registers')},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zr', type=Path, required=True, help='Pinned ZR C1.11 MAIN payload')
    parser.add_argument('--z63', type=Path, required=True, help='Pinned Z6III C2.01 MAIN payload')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.zr, args.z63, args.output)
