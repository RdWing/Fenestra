"""Check native C2.01 job binding with original preparation and builder code.

The fixtures use synthetic frames. These checks do not qualify recording,
hardware order, pixel color, native scheduling, or concurrent access.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.check_zr_color_transplant import Original,load_arm
from host.color_transplant import OFFSETS,PARAMETERS,SAMPLES,SIZE
from host.log3g10_reference import reference
from unicorn import UC_HOOK_CODE
from unicorn.arm64_const import *

JOB=0x11a20
CONTEXT=0xa60
FRAME=0x2cd9
SOURCES=('src/platform/z63_c201/color_job.c','src/platform/z63_c201/color_transplant.c','src/memory.c')


class View(ctypes.Structure):
    _fields_=[(name,kind)for stem in ('job','context','frame','generator_input','generator_output')
              for name,kind in ((stem,ctypes.c_void_p),(stem+'_bytes',ctypes.c_size_t))]+[('generator_result',ctypes.c_int32)]


def build(directory,clang,linker):
    shared=Path(directory)/'job.dylib'
    subprocess.run([clang,'-shared','-fPIC','-O2','-std=c11','-Wall','-Wextra','-Werror',
        '-Wconversion','-Wshadow','-I',str(ROOT/'include'),*[str(ROOT/x)for x in SOURCES],'-o',str(shared)],check=True)
    lib=ctypes.CDLL(str(shared));apply=lib.fx_z63_color_job_apply
    apply.argtypes=[ctypes.POINTER(View),ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,
                   ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p];apply.restype=ctypes.c_int
    scalar=lib.fx_z63_color_job_interpolate;scalar.argtypes=[ctypes.c_uint16,ctypes.c_uint16];scalar.restype=ctypes.c_uint16
    style=lib.fx_z63_color_job_style;style.argtypes=[ctypes.POINTER(View)];style.restype=ctypes.c_int
    objects=[]
    for number,name in enumerate(SOURCES):
        obj=Path(directory)/f'{number}.o';objects.append(str(obj))
        subprocess.run([clang,'--target=aarch64-none-elf','-O2','-ffreestanding','-fno-builtin',
            '-mgeneral-regs-only','-mstrict-align','-fno-stack-protector','-DFX_FREESTANDING=1',
            '-I',str(ROOT/'include'),'-c',str(ROOT/name),'-o',str(obj)],check=True)
    elf=Path(directory)/'color-job.elf'
    subprocess.run([linker,'-m','aarch64elf','-Ttext=0x46000000','--entry=fx_z63_color_job_apply',
                    *objects,'-o',str(elf)],check=True)
    return apply,scalar,style,elf.read_bytes()


def host_tests(apply,style):
    def buffer(n):return (ctypes.c_ubyte*n)()
    j,c,f,i,o,w=map(buffer,(JOB,CONTEXT,FRAME,0x40,8,SIZE))
    view=View(ctypes.addressof(j),JOB,ctypes.addressof(c),CONTEXT,ctypes.addressof(f),FRAME,
              ctypes.addressof(i),0x40,ctypes.addressof(o),8,1)
    def put(buf,offset,value,fmt='Q'):struct.pack_into('<'+fmt,buf,offset,value)
    put(j,0x10,view.context);put(c,0xa58,view.frame);put(i,8,view.frame)
    put(i,0x10,view.job+0x1fe8);put(i,0x18,view.job+0x410);put(o,0,view.job+0x20e8)
    put(c,0x10,7,'I');c[0x51]=c[0x54]=1;put(f,0,1,'I');put(f,0x3a4,3,'I')
    put(j,0x154,1,'I');put(j,0x1c2,256,'H');j[0x1e3b]=j[0x1e3c]=2
    lut=(ctypes.c_uint16*25)(*[1024]*25);curve=(ctypes.c_uint16*229)(*reference()['vectors'][1]['values'])
    stock=bytes(j);count=0
    def call(selected=1,l=lut,n=25,cv=curve,k=229,work=w):
        return apply(ctypes.byref(view),selected,l,n,cv,k,work)
    assert call(0)==0 and bytes(j)==stock
    assert apply(None,0,None,0,None,0,None)==0
    for file in (3,4):
        for cls in (6,7):
            ctypes.memmove(j,stock,JOB);put(f,0x3a4,file,'I');put(c,0x10,cls,'I')
            assert call()==1;count+=1
            changed={n for n,(a,b)in enumerate(zip(stock,bytes(j)))if a!=b}
            permitted=set(range(0x1bd8+0x248,0x1bd8+0x25a))|{0x1bd8+0x263,0x1bd8+0x264}
            for off in OFFSETS:permitted.update(range(0x287c+off,0x287c+off+458))
            assert changed<=permitted and bytes(j)[0x287c+0x16a2:0x287c+0x186c]==stock[0x287c+0x16a2:0x287c+0x186c]
    ctypes.memmove(j,stock,JOB);put(f,0x3a4,3,'I');put(c,0x10,7,'I')
    rejected=0
    mutations=((j,4,1,'B'),(c,0x1b,1,'B'),(c,0x51,0,'B'),(c,0x54,0,'B'),(c,0x55,1,'B'),
               (c,0x10,5,'I'),(c,0x10,8,'I'),(f,0,0,'I'),(f,4,1,'I'),(f,0x618,1,'B'),
               (f,0x2cd8,1,'B'),(f,0x3a4,2,'I'),(f,0x3a4,5,'I'),(f,0x3a4,6,'I'),
               (j,0x154,0,'I'),(j,0x1a5,1,'B'),(j,0x1ad,1,'B'),
               (j,0x10,0,'Q'),(c,0xa58,0,'Q'),(i,8,0,'Q'),(i,0x10,0,'Q'),
               (i,0x18,0,'Q'),(i,0,1,'I'),(o,0,view.job+0x287c,'Q'),
               (j,0x1e3b,3,'B'),(j,0x1e3c,3,'B'))
    for buf,offset,value,fmt in mutations:
        old=bytes(buf);put(buf,offset,value,fmt);before=bytes(j)
        assert call()<0 and bytes(j)==before,(offset,value)
        ctypes.memmove(buf,old,len(buf));rejected+=1
    for field in ('job_bytes','context_bytes','frame_bytes','generator_input_bytes','generator_output_bytes'):
        old=getattr(view,field);setattr(view,field,old-1);before=bytes(j)
        assert call()<0 and bytes(j)==before
        setattr(view,field,old);rejected+=1
    for code in (0,-1,2):
        view.generator_result=code;before=bytes(j)
        assert call()<0 and bytes(j)==before;rejected+=1
    view.generator_result=1
    for args in ({'selected':2},{'n':24},{'k':228},{'work':None},{'work':j},{'work':c},
                 {'work':f},{'work':i},{'work':o},{'work':curve},{'work':lut},{'l':None},{'cv':None}):
        before=bytes(j);assert call(**args)<0 and bytes(j)==before;rejected+=1
    for raw,expected in ((0xffffffff,0),(0x80000000,0),(0,0),(37,37),(38,37),(0x7fffffff,37)):
        put(j,0x1b4,raw,'I');assert style(ctypes.byref(view))==expected
    return {'applied_cases':count,'unchanged_rejections':rejected,'stock_cases':2,'style_cases':6}


def native_scalar_tests(m,scalar):
    m.u.mem_write(0x140000,bytes(0x200));m.u.mem_write(0x150000,bytes(0x200))
    m.put(0x140040,0x150000);m.put(0x1400a0,0x170000);m.put(0x1400f0,0x160000)
    m.put(0x1500b8,1,'I')
    rng=random.Random(0xc201)
    cases=[(value,256)for value in range(65536)]+[(65535,weight)for weight in range(65536)]
    cases += [(rng.randrange(65536),rng.randrange(65536))for _ in range(4096)]
    for value,weight in cases:
        m.put(0x160000,value,'H');m.put(0x150126,weight,'H')
        m.u.reg_write(UC_ARM64_REG_X0,0x140000)
        m.u.emu_start(0x4111d618,0x4111dd04,count=1000)
        assert m.u.reg_read(UC_ARM64_REG_PC)==0x4111dd04
        assert scalar(value,weight)==m.u.reg_read(UC_ARM64_REG_W11),(value,weight)
    return len(cases)


def native_job_tests(m,elf):
    entry=load_arm(m,elf);u=m.u;u.mem_map(0x300000,0x100000)
    j,c,f=0x300000,0x320000,0x330000;view,curve,workspace=0x360000,0x361000,0x370000
    raw=struct.pack('<229H',*reference()['vectors'][1]['values']);u.mem_write(curve,raw)
    pause_at=[0]
    def pause(machine,address,size,data):
        if address==pause_at[0]:machine.emu_stop()
    stop=u.hook_add(UC_HOOK_CODE,pause)
    cases=0;restored=0;builder_pointers=0
    for file in (3,4):
        for cls in (6,7):
            u.mem_write(j,bytes(JOB));u.mem_write(c,bytes(CONTEXT));u.mem_write(f,bytes(FRAME))
            m.put(j+0x10,c);m.put(c+0xa58,f);m.put(c+0x10,cls,'I');m.put(c+0x51,1,'B')
            m.put(f,1,'I');m.put(f+0x3a4,file,'I');m.put(j+0x154,1,'I');m.put(j+0x1c2,256,'H')
            u.mem_write(f+0x5c6,struct.pack('<10h',1,16384,0,0,0,16384,0,0,0,16384))
            saved=None
            for selected in (1,0):
                u.mem_write(0xa03d2a08c,bytes(5*0x2c0));m.put(0xa03d2ae4c,0,'I');m.put(c+0x55,0,'B')
                assert m.run(0x40e724ec,j)==0 and m.get(c+0x54,'B')==1
                u.reg_write(UC_ARM64_REG_SP,0x1fe000);u.reg_write(UC_ARM64_REG_LR,0x1ffff0);u.reg_write(UC_ARM64_REG_X0,j)
                pause_at[0]=0x40e72798;u.emu_start(0x40e7261c,0x1ffff0,count=1000000)
                assert u.reg_read(UC_ARM64_REG_PC)==0x40e72798
                inp,out=u.reg_read(UC_ARM64_REG_X0),u.reg_read(UC_ARM64_REG_X1)
                pause_at[0]=0x40e7279c;u.emu_start(0x40e72798,0x1ffff0,count=1000000)
                assert u.reg_read(UC_ARM64_REG_PC)==0x40e7279c and u.reg_read(UC_ARM64_REG_X0)==1
                assert m.get(c+0x55,'B')==0
                snapshot=(bytes(u.mem_read(j+0x1bd8,PARAMETERS)),bytes(u.mem_read(j+0x287c,SAMPLES)))
                if saved is None:saved=snapshot
                else:assert snapshot==saved;restored+=1
                u.mem_write(view,struct.pack('<10Qi4x',j,JOB,c,CONTEXT,f,FRAME,inp,0x40,out,8,1))
                lut=m.get(0xa02af8de0)
                original_context=u.context_save()
                u.reg_write(UC_ARM64_REG_SP,0x1d0000);u.reg_write(UC_ARM64_REG_LR,0x1ffff0)
                for k,arg in enumerate((view,selected,lut,25,curve,229,workspace)):u.reg_write(UC_ARM64_REG_X0+k,arg)
                u.emu_start(entry,0x1ffff0,count=1000000)
                assert u.reg_read(UC_ARM64_REG_PC)==0x1ffff0 and u.reg_read(UC_ARM64_REG_X0)==selected
                assert m.get(c+0x55,'B')==0
                u.context_restore(original_context);pause_at[0]=0;u.emu_start(0x40e7279c,0x1ffff0,count=1000000)
                assert u.reg_read(UC_ARM64_REG_PC)==0x1ffff0 and m.get(c+0x55,'B')==1
                assert bytes(u.mem_read(j+0x287c+0x16a2,458))==saved[1][0x16a2:0x186c]
                u.mem_write(0x140000,bytes(0x480));u.mem_write(0x141000,bytes(0x600))
                m.put(0x140400,j+0x1bd8);m.put(0x140418,j+0x20e8)
                m.run(0x40e60664,0,0x140000,0x141000)
                for k,off in enumerate((*OFFSETS,0x16a2)):
                    ptr=m.get(0x141458+8*k);assert ptr==j+0x287c+off;builder_pointers+=1
                    if selected and k<6:assert bytes(u.mem_read(ptr,458))==raw
                if not selected:
                    assert bytes(u.mem_read(j+0x1bd8,PARAMETERS))==saved[0]
                    assert bytes(u.mem_read(j+0x287c,SAMPLES))==saved[1]
                cases+=1
    u.hook_del(stop)
    return {'complete_original_job_cycles':cases,'stock_restorations':restored,
            'complete_static_builder_pointers':builder_pointers,'mocked_helpers':[]}


def static_graph_contract(m):
    """Check the complete initialized graph, separate from instruction tests."""
    start=0xa02be2000;size=0x48190;blob=m.blob[0x546f000:0x546f000+size]
    def read(address,count):
        assert start<=address and address+count<=start+size
        return blob[address-start:address-start+count]
    result={}
    for cls,address,slots,consumer_stage in ((6,0xa02be3e28,[0,1,2,3,4,15,16,30,31,45],3),
                                           (7,0xa02be2320,[0,1,2,3,15,16,30,31,45,46],2)):
        matrix=struct.unpack('<165Q',read(address,165*8));assert [i for i,p in enumerate(matrix)if p]==slots
        stages=[]
        for index,descriptor in enumerate(matrix):
            if not descriptor:continue
            fields=struct.unpack('<10Q',read(descriptor,80));actions=[]
            for n in range(20):
                record=struct.unpack('<3Q',read(fields[5]+24*n,24))
                if not record[2]:break
                actions.append(record[2])
            else:raise AssertionError('unterminated action list')
            if index==0:
                assert fields[0]==1 and fields[1]==0xa029384f8
                assert actions[-2:]==[0x40e73040,0x40e731f4]
            for consumer in (0x40e76090,0x40e76298):
                if consumer in actions:assert index==consumer_stage and fields[0]==1
            assert not set(actions)&{0x40e76684,0x40e77cd8,0x40e78318}
            stages.append({'lane':index//15,'substage':index%15,'descriptor':hex(descriptor),
                           'type':fields[0],'task':hex(fields[1]),'actions':[hex(a)for a in actions]})
        assert all(p==0 for p in matrix[64:])
        result[str(cls)]={'address':hex(address),'entries':165,'bytes':1320,
                          'sha256':hashlib.sha256(read(address,1320)).hexdigest(),'stages':stages}
    return {'evidence':'static initialized source graph; no scheduler execution',
            'graphs':result,'runtime_graph_mutation_checked':False,'indirect_consumer_census_complete':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--z63',required=True)
    p.add_argument('--clang',required=True);p.add_argument('--linker',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();m=Original(a.z63,'z63')
    with tempfile.TemporaryDirectory()as temp:
        apply,scalar,style,elf=build(temp,a.clang,a.linker)
        result={'passed':True,'host':host_tests(apply,style),
                'original_scalar_cases':native_scalar_tests(m,scalar),'original_job':native_job_tests(m,elf),
                'static_graph':static_graph_contract(m),
                'firmware_sha256':hashlib.sha256(m.blob).hexdigest(),
                'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in
                    (*SOURCES,'src/platform/z63_c201/color_job.h','src/platform/z63_c201/color_transplant.h',
                     'host/check_z63_color_job.py','host/check_zr_color_transplant.py','host/color_transplant.py',
                     'host/log3g10_reference.py','host/log3g10_reference.json')},
                'regions':[m.region(address,size)for address,size in ((0x40e724ec,0x130),(0x40e7261c,0x1f8),
                    (0x4104af9c,0x118),(0x4104b494,0xf4),(0x4111c854,0xe4),(0x4111d618,0x934),
                    (0x40e60664,0x4f8),(0x40e80864,0x48),(0x40e7e0cc,0x1c))],
                'compiler':subprocess.check_output([a.clang,'--version'],text=True).strip(),
                'linker':subprocess.check_output([a.linker,'--version'],text=True).strip(),
                'elf_sha256':hashlib.sha256(elf).hexdigest(),'native_hook_installed':False,
                'native_concurrency_tested':False,'pixel_basis_proved':False,'recording_qualified':False}
        output=Path(a.output);output.mkdir(parents=True,exist_ok=False)
        (output/'color-job.elf').write_bytes(elf);(output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))


if __name__=='__main__':main()
