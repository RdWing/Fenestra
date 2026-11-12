"""Account for every observed C2.01 model NOR operation, without sampling.

The default profile permits the two observed activation-save slices. The
explicit video profile checks original registry rows before admitting the full
settings banks and native backend 33. Firmware updates need a different profile. Observed CPU
transactions and modeled completion do not establish physical flash behavior.
"""
import hashlib
import json
import struct
from pathlib import Path

BANKS=((0x45e20000,0x45e40000),(0x46220000,0x46240000))


def regions(profile,application=None):
    if profile=='activation':return BANKS,[]
    if profile!='video-settings' or application is None:raise ValueError('video profile requires the pinned C2.01 registry')
    image=Path(application).read_bytes()
    if len(image) not in (88830365,88830367):raise ValueError('C2.01 application extent differs')
    bounds=[];sources=[]
    for index,offset,digest in (
        (16,0x51bbf80,'9111a330bfe6c744d32f1df0300ffb05bb8c7e5466858b784b6a0fc1c257e1cd'),
        (33,0x51bc228,'d7241210ce71b67a8db78c5e738a12bd6cf857deb92e468be528766529382038')):
        row=image[offset:offset+40]
        if hashlib.sha256(row).hexdigest()!=digest:raise ValueError('C2.01 storage registry row differs')
        primary,alternate,capacity=struct.unpack_from('<QQI',row)
        bounds.extend((base,base+capacity) for base in (primary,alternate))
        sources.append(dict(backend=index,offset=hex(offset),bytes=40,sha256=digest))
    return tuple(bounds),sources


def audit(path,*,profile='activation',application=None):
    banks,sources=regions(profile,application)
    lines=Path(path).read_text().splitlines()
    if not lines or not lines[0].startswith('FXNOR1 '):raise ValueError('missing trace header')
    if not lines[-1].startswith('END '):raise ValueError('incomplete NOR trace')
    registers={};pending=None;operations=[];expected=0;last_command=0;stores=0
    for line in lines[1:-1]:
        fields=line.split()
        if len(fields)!=8:raise ValueError('invalid NOR event')
        seq,cpu=int(fields[0]),int(fields[1]);kind=fields[2]
        pc,address=int(fields[3],16),int(fields[4],16)
        size,value,supported=int(fields[5]),int(fields[6],16),int(fields[7])
        if seq!=expected or kind not in ('W','R') or not supported:raise ValueError('missing or unsupported event')
        expected+=1
        if 0x40000000<=address<0x48000000:
            if kind!='W' or not pending or pending['kind']!='program':raise ValueError('NOR store outside a program')
            if address!=pending['address']+pending['received'] or size>pending['bytes']-pending['received']:
                raise ValueError('program destination/extent/order differs')
            pending['received']+=size;stores+=1
            continue
        if not 0x0e007000<=address<0x0e007100 or size!=4:raise ValueError('controller transaction differs')
        offset=address-0x0e007000
        if kind=='W':
            registers[offset]=value
            if offset==0x90:
                last_command=value
                lengths={0xdc0b0001:65536,0x5c0b0001:32768,0x210b0001:4096}
                if value in lengths:
                    if pending:raise ValueError('overlapping NOR operations')
                    pending=dict(kind='erase',address=0x40000000+registers[0x94],bytes=lengths[value],
                                 received=0,started=seq,pc=hex(pc),cpu=cpu)
            elif offset==0x70 and value==1:
                if pending:raise ValueError('overlapping NOR operations')
                n=registers.get(0x7c,0);at=registers.get(0x78,-1)
                if not 0<n<=256 or at<0 or at//256!=(at+n-1)//256 or registers.get(0x1c)!=at:
                    raise ValueError('invalid page program setup')
                pending=dict(kind='program',address=0x40000000+at,bytes=n,received=0,
                             started=seq,pc=hex(pc),cpu=cpu)
            if pending and not any(lo<=pending['address'] and pending['address']+pending['bytes']<=hi for lo,hi in banks):
                raise ValueError('NOR operation outside the permitted profile: '+hex(pending['address']))
        elif pending:
            done=False
            if offset==0xa0 and last_command==0x70930401 and value&0x30:raise ValueError('NOR error status')
            if pending['kind']=='erase' and offset==0xa0:
                done=(last_command==0x05930401 and not value&1) or (last_command==0x70930401 and bool(value&0x80))
            elif pending['kind']=='program' and offset==0x70 and value&0x20:
                if pending['received']!=pending['bytes']:raise ValueError('completion before all program bytes')
                done=True
            if done:
                pending['completed']=seq;pending['address']=hex(pending['address'])
                operations.append(pending);pending=None
    if pending or int(lines[-1].split()[1])!=expected:raise ValueError('unfinished operation or truncated events')
    return dict(passed=True,trace_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                cpu_events=expected,nor_stores=stores,operations=operations,
                erases=sum(r['kind']=='erase' for r in operations),programs=sum(r['kind']=='program' for r in operations),
                profile=profile,registry_sources=sources,
                permitted_regions=[[hex(a),hex(b)] for a,b in banks],
                scope=__doc__,physical_camera_tested=False)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--profile',choices=('activation','video-settings'),default='activation')
    p.add_argument('--application',type=Path)
    a=p.parse_args()
    if a.output.exists():raise ValueError('new output required')
    r=audit(a.trace,profile=a.profile,application=a.application);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:v for k,v in r.items() if k!='operations'},indent=2))
