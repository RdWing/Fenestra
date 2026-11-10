#!/usr/bin/env python3
"""Check bounded malformed CUBE inputs with the original ZR parser."""
from pathlib import Path
import argparse
import hashlib
import json
import struct
try:
    from .check_zr_lut_source import Original, loader_sha256, write_result
except ImportError:
    from check_zr_lut_source import Original, loader_sha256, write_result


def verify(zr_path, output):
    z=Original(zr_path,'zr')
    prefix=b'LUT_3D_SIZE 17\n\n'
    cases=[('empty',b'',0xffffffff),
           ('missing_size',b'0.00000000 0.00000000 0.00000000\n',0xffffffff),
           ('unsupported_size',b'LUT_3D_SIZE 18\n\n',0xffffffff),
           ('truncated',prefix+b'0.00000000 0.00000000 0.00000000\n',0xfffffc17),
           ('negative_output',prefix+b'-0.10000000 0.00000000 0.00000000\n',0xfffffc18),
           ('malformed_triplet',prefix+b'0.00000000 nope 0.00000000\n',0xfffffc18),
           ('above_one_then_truncated',prefix+b'1.20000000 0.00000000 0.00000000\n',0xfffffc17)]
    results=[]
    for name,source,expected in cases:
        z.u.mem_write(0x140000,source+bytes(64))
        z.u.mem_write(0x150000,b'\xa5'*(0x7340+32))
        result=z.run(0x4130c3c0,0x140000,len(source),0x444177f0,0x150010)&0xffffffff
        assert result==expected,(name,hex(result),hex(expected))
        assert bytes(z.u.mem_read(0x150000,16))==b'\xa5'*16
        assert bytes(z.u.mem_read(0x157350,16))==b'\xa5'*16
        if name=='above_one_then_truncated':
            assert tuple(struct.unpack('<3H',z.u.mem_read(0x150010,6)))==(1223,1356,4095)
        results.append({'name':name,'source_sha256':hashlib.sha256(source).hexdigest(),'return_u32':hex(result)})
    out={'passed':True,'cases':results,'firmware_sha256':hashlib.sha256(z.blob).hexdigest(),
         'loader_source_sha256':loader_sha256(),
         'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'limit':'Original parser with bounded synthetic inputs. No filesystem or camera execution.'}
    write_result(output, out)
    print(json.dumps(out,indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zr', type=Path, required=True, help='Pinned ZR C1.11 MAIN payload')
    parser.add_argument('--output', type=Path, required=True, help='Result JSON path')
    args = parser.parse_args()
    verify(args.zr, args.output)
