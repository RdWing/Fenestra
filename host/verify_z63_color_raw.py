"""Check exact C2.01 source bindings and the recovered NRMT dispatch join."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
ROOT=Path(__file__).resolve().parents[1]

def verify(image):
    p=json.loads((ROOT/'targets/z63-c201-color-raw.json').read_text())
    if hashlib.sha256(image).hexdigest()!=p['payload_sha256']:
        raise ValueError('C2.01 payload identity differs')
    rows={r['name']:r for r in p['bindings']}
    def block(name):
        r=rows[name];at=r['address']-p['image_base'];b=image[at:at+r['bytes']]
        if len(b)!=r['bytes'] or hashlib.sha256(b).hexdigest()!=r['sha256']:
            raise ValueError('source binding differs: '+name)
        return b
    for name in rows:block(name)
    fn,tag=struct.unpack_from('<QQ',block('frame_metadata_descriptors'),18*16)
    if fn!=rows['frame_matrix']['address'] or tag!=p['nrmt_matrix_tag']:
        raise ValueError('NRMT matrix dispatch differs')
    for caller in p['description_callers']:
        word=struct.unpack_from('<I',image,caller-p['image_base'])[0]
        delta=word&0x3ffffff
        if delta&(1<<25):delta-=1<<26
        if word>>26!=0x25 or caller+4*delta!=rows['raw_description']['address']:
            raise ValueError('description caller differs')
    return {'bindings':len(rows),'description_callers':3,'matrix_callback':hex(fn),
            'runtime_qualified':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('payload',type=Path)
    print(json.dumps(verify(ap.parse_args().payload.read_bytes()),indent=2))
