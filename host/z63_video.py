"""Local ProRes assets; original bytes are generated only from pinned input."""
import hashlib
import struct
from pathlib import Path


def generate(profile, original, output):
    base=profile['image_base'];p=profile['video_quality'];out=Path(output)
    for r in [*p['hooks'],*p['dependencies']]:
        at=r['address']-base
        if hashlib.sha256(original[at:at+r['bytes']]).hexdigest()!=r['sha256']:
            raise ValueError('video preimage differs: '+r['name'])
    def block(address,size):return original[address-base:address-base+size]
    rows=[]
    for q,(num,den) in enumerate([(1,1),(147,220),(102,220),(45,220)]):
        rate=bytearray(block(0x42b72828,288))
        for i in range(12):
            value=struct.unpack_from('<Q',rate,i*24+16)[0]
            if not value or value%(10<<20):raise ValueError('video rate geometry differs')
            if q:struct.pack_into('<Q',rate,i*24+16,((value*num+den*(1<<19))//(den*(1<<20)))<<20)
        rows.append(rate)
    def bytes_array(name,rows):
        n=len(rows[0]);return f'_Alignas(8) static const unsigned char {name}[{len(rows)}][{n}]={{\n'+\
            ',\n'.join('{'+','.join(map(str,row))+'}' for row in rows)+'\n};\n'
    header='/* Generated from the complete locally supplied original C2.01 EG. */\n'
    header+=bytes_array('fx_z63_video_rates',rows)
    templates=[]
    for q,label in enumerate([b'Apple ProRes 422 HQ',b'Apple ProRes 422',b'Apple ProRes 422 LT',b'Apple ProRes 422 Proxy']):
        row=bytearray(block(0x42b7145a,86));row[7]=b'hnso'[q];row[50]=len(label);row[51:82]=label.ljust(31,b'\0');templates.append(row)
    if templates[0]!=block(0x42b7145a,86):raise ValueError('HQ template not preserved')
    header+=bytes_array('fx_z63_video_templates',templates)
    shoot=list(struct.unpack('<14Q',block(0x4408a060,112)));matches=[i for i in range(0,14,2) if shoot[i]==4]
    if len(matches)!=1:raise ValueError('video shooting table differs')
    header+='static const char fx_z63_video_labels[4][16]={"ProRes 422 HQ","ProRes 422","ProRes 422 LT","ProRes Proxy"};\n'
    header+='static const uint64_t fx_z63_video_shoot_tables[4][14]={\n'
    for q in range(4):
        values=[f'UINT64_C({v})' for v in shoot];values[matches[0]+1]=f'(uintptr_t)fx_z63_video_labels[{q}]'
        header+='{'+','.join(values)+'},\n'
    header+='};\n';(out/'z63_video_assets.h').write_text(header)
    assembly=['/* Locally generated original entry instructions. */','.text']
    for row in p['original_entries']:
        size=row.get('bytes',4);words=struct.unpack('<'+'I'*(size//4),block(row['address'],size));word=words[0]
        # Only STP, pre-indexed STR or SUB SP,SP immediate are moved.
        if row['name']=='play_stock':
            if size!=132:raise ValueError('Stock playback block differs')
            # Reviewed block: MOV/MOVK, stack/constant loads/stores and one
            # local B. Its branch displacement stays within this copied block.
            for i,w in enumerate(words):
                if w&0x7c000000==0x14000000:
                    delta=w&0x3ffffff
                    if delta&(1<<25):delta-=1<<26
                    if w>>26!=5 or not 0<=i+delta<len(words):raise ValueError('external Stock playback branch')
        elif size!=4 or not (word&0x3a000000==0x28000000 or word&0xffe00fff==0xf8000ffe or word&0xffc003ff==0xd10003ff):
            raise ValueError('unsupported original video entry')
        name='fx_z63_video_'+row['name']+'_original'
        assembly+=['.p2align 2','.global '+name,name+':',*[f'.inst 0x{w:08x}' for w in words],'b '+name+'_return']
    (out/'z63_video_original.inc').write_text('\n'.join(assembly)+'\n')
    shoot_words=struct.unpack('<7I',block(0x40519a20,28))
    (out/'z63_video_shoot_count.inc').write_text('\n'.join(f'.inst 0x{shoot_words[i]:08x}' for i in (1,3,5))+'\n')
    (out/'z63_video_parser_compare.inc').write_text('\n'.join(f'.inst 0x{w:08x}' for w in struct.unpack('<3I',block(0x40ceb330,12)))+'\n')
    returns=dict(p['returns'])
    returns.update({'fx_z63_video_'+r['name']+'_original_return':r['address']+r.get('bytes',4) for r in p['original_entries']})
    return returns
