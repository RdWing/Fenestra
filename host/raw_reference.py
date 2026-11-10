"""Independent bounded BMFF/NRMT inspection for offline compatibility tests."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def boxes(data,start,end):
    while start<end:
        if end-start<8:raise ValueError('truncated box header')
        size,kind=struct.unpack_from('>I4s',data,start);header=8
        if size==1:
            if end-start<16:raise ValueError('truncated extended box')
            size=struct.unpack_from('>Q',data,start+8)[0];header=16
        elif size==0:size=end-start
        if size<header or size>end-start:raise ValueError('box exceeds parent')
        yield kind,start+header,start+size
        start+=size


def one(data,start,end,kind):
    hits=[(a,b) for k,a,b in boxes(data,start,end) if k==kind]
    if len(hits)!=1:raise ValueError('missing or duplicate '+repr(kind))
    return hits[0]


def movie_bounds(data):
    top=list(boxes(data,0,len(data)))
    if any(k==b'moof' for k,_,_ in top):raise ValueError('fragmented movies are unsupported')
    moov=one(data,0,len(data),b'moov')
    if any(k==b'mvex' for k,_,_ in boxes(data,*moov)):raise ValueError('fragmented movies are unsupported')
    return moov,[(a,b) for k,a,b in top if k==b'mdat']


def table(data,start,end,width):
    if end-start<8:raise ValueError('truncated table')
    n=struct.unpack_from('>I',data,start+4)[0]
    if n>(end-start-8)//width or end-start!=8+n*width:raise ValueError('invalid table count')
    return [data[start+8+i*width:start+8+(i+1)*width] for i in range(n)]


def samples(data,track):
    a,b=one(data,*track,b'mdia');a,b=one(data,a,b,b'minf');a,b=one(data,a,b,b'stbl')
    sa,sb=one(data,a,b,b'stsz')
    if sb-sa<12:raise ValueError('truncated sample sizes')
    fixed,count=struct.unpack_from('>II',data,sa+4)
    if count>len(data):raise ValueError('impossible sample count')
    if fixed:
        if sb-sa!=12:raise ValueError('invalid fixed size table')
        sizes=[fixed]*count
    else:
        if sb-sa!=12+4*count:raise ValueError('invalid variable size table')
        sizes=list(struct.unpack_from('>'+str(count)+'I',data,sa+12))
    chunks=[(k,x,y) for k,x,y in boxes(data,a,b) if k in (b'stco',b'co64')]
    if len(chunks)!=1:raise ValueError('missing chunk table')
    k,x,y=chunks[0];fmt='>I' if k==b'stco' else '>Q'
    offsets=[struct.unpack(fmt,row)[0] for row in table(data,x,y,struct.calcsize(fmt))]
    x,y=one(data,a,b,b'stsc');runs=[struct.unpack('>III',r) for r in table(data,x,y,12)]
    if not runs or runs[0][0]!=1 or any(not n or d!=1 for _,n,d in runs):raise ValueError('unsupported chunk mapping')
    if any(runs[i][0]>=runs[i+1][0] for i in range(len(runs)-1)):raise ValueError('unordered chunk runs')
    result=[];sample=0;run=0
    for chunk,offset in enumerate(offsets,1):
        while run+1<len(runs) and runs[run+1][0]<=chunk:run+=1
        for _ in range(runs[run][1]):
            if sample>=count:raise ValueError('too many chunk samples')
            size=sizes[sample]
            if size>len(data)-offset:raise ValueError('sample exceeds file')
            result.append((offset,size));offset+=size;sample+=1
    if sample!=count:raise ValueError('unmapped samples')
    return result


def frame(data,start,size):
    end=start+size
    if size<8 or struct.unpack_from('>I4s',data,start)!=(size,b'NRAW'):raise ValueError('invalid RAW sample')
    pos=start+8;tags={};codestream=None
    while pos<end:
        if data[pos:pos+2]==b'\xff\x10':codestream=pos;break
        kind,a,b=next(boxes(data,pos,end));box_start=pos
        if kind==b'NRFH':
            for k,x,y in boxes(data,a,b):
                if k==b'NRMT':
                    if y-x<4:raise ValueError('short NRMT key')
                    key=struct.unpack_from('>I',data,x)[0]
                    if key in tags:raise ValueError('duplicate NRMT key')
                    tags[key]=(x+4,y-x-4)
        pos=b
        if pos<=box_start:raise ValueError('nonadvancing sample')
    if codestream is None:raise ValueError('missing codestream')
    return codestream,tags


def inspect(path):
    data=Path(path).read_bytes();(a,b),media=movie_bounds(data)
    tracks=[(x,y) for k,x,y in boxes(data,a,b) if k==b'trak'];video=[];audio=[]
    for track in tracks:
        x,y=one(data,*track,b'mdia');h,_=one(data,x,y,b'hdlr');kind=data[h+8:h+12]
        for off,size in samples(data,track):
            if not any(a<=off and off+size<=b for a,b in media):raise ValueError('sample outside media box')
            if kind==b'vide':
                cs,tags=frame(data,off,size)
                video.append({'codestream':hashlib.sha256(data[cs:off+size]).hexdigest(),
                    'tags':{hex(k):data[p:p+n].hex() for k,(p,n) in tags.items()}})
            elif kind==b'soun':audio.append(hashlib.sha256(data[off:off+size]).hexdigest())
    if not video:raise ValueError('missing video')
    return {'sha256':hashlib.sha256(data).hexdigest(),'video':video,'audio':audio}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('output');a=p.parse_args()
    left,right=inspect(a.source),inspect(a.output)
    if [r['codestream'] for r in left['video']]!=[r['codestream'] for r in right['video']]:raise ValueError('RAW codestreams differ')
    if left['audio']!=right['audio']:raise ValueError('audio samples differ')
    print(json.dumps({'source_sha256':left['sha256'],'output_sha256':right['sha256'],
        'frames':len(left['video']),'audio_samples':len(left['audio']),
        'codestreams_identical':True,'audio_identical':True},indent=2))
