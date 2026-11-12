"""Resolve a local ELF64 function by its compilation unit, without name loss."""
import struct
from pathlib import Path


def local_function(path,unit,name):
    data=Path(path).read_bytes()
    if data[:6]!=b'\x7fELF\x02\x01':raise ValueError('little-endian ELF64 required')
    offset=struct.unpack_from('<Q',data,40)[0]
    stride,count=struct.unpack_from('<HH',data,58)
    if stride!=64 or not count or offset+stride*count>len(data):raise ValueError('invalid ELF sections')
    sections=[struct.unpack_from('<II4QII2Q',data,offset+i*stride) for i in range(count)]
    matches=[]
    for section in sections:
        if section[1]!=2:continue
        if section[9]!=24 or section[6]>=len(sections):raise ValueError('invalid ELF symbols')
        strings=sections[section[6]];names=data[strings[4]:strings[4]+strings[5]]
        owner=None
        for at in range(section[4],section[4]+section[5],24):
            key,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,at)
            end=names.find(b'\0',key)
            if end<key:raise ValueError('unterminated ELF name')
            symbol=names[key:end].decode()
            if info&15==4:owner=symbol
            if info==2 and owner==unit and symbol==name:
                if not size or index>=len(sections):raise ValueError('invalid function extent')
                text=sections[index];position=text[4]+value-text[3]
                if value<text[3] or value+size>text[3]+text[5] or position+size>len(data):
                    raise ValueError('function outside its section')
                matches.append((value,data[position:position+size]))
    if len(matches)!=1:raise ValueError('local function is absent or ambiguous: '+unit+':'+name)
    return matches[0]
