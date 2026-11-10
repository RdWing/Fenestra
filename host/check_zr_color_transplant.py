"""Compare a C2.01 color candidate with original ZR code, then test transport.

The candidate has no recording hook. Synthetic inputs and register memory do
not establish the pixel basis, hardware order, or an accepted recording mode.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.log3g10_reference import reference
from host.color_transplant import library,PARAMETERS,SAMPLES,SIZE,OFFSETS
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
from unicorn.arm64_const import *

PINS={'z63':'236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87',
      'zr':'9ac53c082e1d7cc841c458465c08bb49223b36cf9d381b8206076751d7b42c8f'}
BASE=0x40160000


class Original:
    def __init__(self,path,model):
        self.blob=Path(path).read_bytes()
        if hashlib.sha256(self.blob).hexdigest()!=PINS[model]:raise ValueError('firmware identity differs: '+model)
        self.u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u=self.u
        u.mem_map(BASE,(len(self.blob)+4095)&~4095);u.mem_write(BASE,self.blob)
        u.mem_map(0xa02800000,0x4000000)
        start,size=(0x4f57000,0x472000) if model=='zr' else (0x5095000,0x3d9028)
        u.mem_write(0xa02808000,self.blob[start:start+size]);u.mem_map(0x100000,0x100000)
        u.reg_write(UC_ARM64_REG_CPACR_EL1,3<<20)

    def put(self,a,v,fmt='Q'):self.u.mem_write(a,struct.pack('<'+fmt,v))
    def get(self,a,fmt='Q'):return struct.unpack('<'+fmt,self.u.mem_read(a,struct.calcsize('<'+fmt)))[0]
    def run(self,pc,*args):
        u=self.u;u.reg_write(UC_ARM64_REG_SP,0x1fe000);u.reg_write(UC_ARM64_REG_LR,0x1ffff0)
        for i in range(8):u.reg_write(UC_ARM64_REG_X0+i,args[i] if i<len(args) else 0)
        u.emu_start(pc,0x1ffff0,count=1000000)
        if u.reg_read(UC_ARM64_REG_PC)!=0x1ffff0:raise AssertionError('instruction bound reached')
        return u.reg_read(UC_ARM64_REG_X0)

    def region(self,a,n):return {'address':hex(a),'bytes':n,'sha256':hashlib.sha256(self.blob[a-BASE:a-BASE+n]).hexdigest()}


def build_arm(directory,clang,linker):
    objects=[]
    for i,name in enumerate(('src/platform/z63_c201/color_transplant.c','src/memory.c')):
        obj=Path(directory)/f'{i}.o';objects.append(str(obj))
        subprocess.run([clang,'--target=aarch64-none-elf','-O2','-ffreestanding','-fno-builtin',
            '-mgeneral-regs-only','-mstrict-align','-fno-stack-protector','-DFX_FREESTANDING=1',
            '-I',str(ROOT/'include'),'-c',str(ROOT/name),'-o',str(obj)],check=True)
    elf=Path(directory)/'color-transplant.elf'
    subprocess.run([linker,'-m','aarch64elf','-Ttext=0x46000000','--entry=fx_z63_color_transplant',
                    *objects,'-o',str(elf)],check=True)
    return elf.read_bytes()


def load_arm(machine,elf):
    off=struct.unpack_from('<Q',elf,32)[0];size,count=struct.unpack_from('<HH',elf,54)
    mapped=set()
    for i in range(count):
        kind,flags,pos,address,physical,filesize,memsize,alignment=struct.unpack_from('<II6Q',elf,off+i*size)
        if kind!=1:continue
        for page in range(address&~4095,(address+memsize+4095)&~4095,4096):
            if page not in mapped:machine.u.mem_map(page,4096);mapped.add(page)
        machine.u.mem_write(address,elf[pos:pos+filesize])
    return struct.unpack_from('<Q',elf,24)[0]


def verify(z63,zr,clang,linker,output,calibration_path):
    c=Original(z63,'z63');z=Original(zr,'zr');d=reference()
    calibration_blob=Path(calibration_path).read_bytes()
    calibration_sha=hashlib.sha256(calibration_blob).hexdigest()
    if calibration_sha!='c6077054bc98831579b8d89f8da4e0e90b098c04749950afca62eb0987d4dc98':
        raise ValueError('supplied ZR calibration identity differs')
    calibration_pair=calibration_blob[0x117b40:0x117b66]
    assert struct.unpack('<19h',calibration_pair)==(1,16243,99,42,-87,16534,-63,-11,-7,16402,16526,-99,-43,87,16235,62,11,7,16366)
    # The fourth row is new; it is not a new M1 gamut matrix.
    zr_spaces=bytes(z.u.mem_read(0xa02a1a3e0,90));c_spaces=bytes(c.u.mem_read(0xa029e8e06,72))
    assert zr_spaces[:72]==c_spaces
    assert struct.unpack('<9h',zr_spaces[72:])==(1024,0,0,0,1024,0,0,0,1024)
    assert z.u.mem_read(0xa02a1a31a,198)==c.u.mem_read(0xa029e8d40,198)
    assert z.u.mem_read(0xa02a1a43a,14)==c.u.mem_read(0xa029e8e4e,14)
    nlg=bytes(z.u.mem_read(0xa02a1be0a+3*458,458))
    assert nlg==bytes(z.u.mem_read(0xa02a1be0a+458,458))==bytes(c.u.mem_read(0xa029ea808,458))
    # The upstream M1 source is the sensor resource's calibration pair. Execute
    # both complete public getters, including their native copy functions.
    for machine,slot,getter in ((c,0xa04ce57f0,0x40f4638c),(z,0xa057b0340,0x4114c2b8)):
        machine.u.mem_map(0x30000000,0x140000);machine.put(slot,0x30000000)
        vectors=[struct.pack('<19H',valid,*[(k*8191)&65535 for k in range(18)])for valid in (0,1,65535)]
        vectors.append(calibration_pair)
        for calibration in vectors:
            machine.u.mem_write(0x30117b40,calibration);machine.u.mem_write(0x180000,b'\xa5'*70)
            machine.run(getter,0x180010)
            assert bytes(machine.u.mem_read(0x180010,38))==calibration
            assert bytes(machine.u.mem_read(0x180000,16))==b'\xa5'*16
            assert bytes(machine.u.mem_read(0x180036,16))==b'\xa5'*16
    # Compare the complete M1 producers with corresponding prepared layouts.
    m1_cases=0
    for row in range(11):
        for weight in (0,26,128,230,256):
            for scale in range(7):
                for calibration in ((16384,0,0,0,16384,0,0,0,16384),(18000,-1000,500,700,16000,-400,-200,300,17000)):
                    values=[]
                    for m,pc,delta,tone in ((c,0x4111cd60,0,1),(z,0x41311340,4,3)):
                        m.u.mem_write(0x140000,bytes(0x200));m.u.mem_write(0x150000,bytes(0x200))
                        m.put(0x140000,0x160000);m.put(0x140040,0x150000);m.put(0x1400a0,0x170000)
                        m.u.mem_write(0x160000,struct.pack('<10h',1,*calibration))
                        m.put(0x150106+delta,1,'B');m.put(0x15003c,127+row,'I')
                        m.put(0x150126+delta,weight,'H');m.put(0x1500b8,tone,'I');m.put(0x1500bc,scale,'I')
                        m.run(pc,0x140000);values.append(bytes(m.u.mem_read(0x170010,20)))
                    assert values[0]==values[1];m1_cases+=1
    with tempfile.TemporaryDirectory() as tmp:
        lib,fn=library(tmp);elf=build_arm(tmp,clang,linker);entry=load_arm(c,elf)
        p=(ctypes.c_ubyte*PARAMETERS)();p[0x263]=p[0x264]=2
        samples=bytearray((i*17+23)&255 for i in range(SAMPLES));samples[0x16a2:0x186c]=nlg
        s=(ctypes.c_ubyte*SAMPLES).from_buffer_copy(samples);out=(ctypes.c_ubyte*SIZE)()
        vector=(ctypes.c_uint16*229)(*d['vectors'][1]['values'])
        z.u.mem_write(0x140000,bytes(0x200));z.u.mem_write(0x150000,bytes(0x200))
        z.put(0x140040,0x150000);z.put(0x1400a0,0x170000);z.put(0x1400f0,0x160000)
        z.put(0x15012a,256,'H');z.put(0x1500b8,3,'I')
        for gain in range(65536):
            z.put(0x160000,gain,'H');z.run(0x41311dbc,0x140000)
            assert fn(out,p,PARAMETERS,s,SAMPLES,vector,229,gain)==1
            assert bytes(out)[0x248:0x25a]==bytes(z.u.mem_read(0x170070,18)),gain
        # Full original serializers supply the control bytes, independently of
        # the isolated M2 test. Only tone changes between these two fixtures.
        serial=[]
        for machine,serializer,tone,weight_offset in ((z,0x4130e7d8,1,0x12a),(z,0x4130e7d8,3,0x12a),(c,0x4111a7f4,1,0x126)):
            for a,n in ((0x140000,0x2000),(0x150000,0x200),(0x160000,0x200),(0x170000,0x2000),(0x180000,0x2000),(0x190000,0x2000)):
                machine.u.mem_write(a,bytes(n))
            machine.put(0x140000,0x160000);machine.put(0x140010,0x150000);machine.put(0x140018,0x170000)
            machine.put(0x141000,0x160100);machine.put(0x141008,0x180000);machine.put(0x141010,0x190000)
            machine.u.mem_write(0x160000,struct.pack('<10h',1,16384,0,0,0,16384,0,0,0,16384))
            machine.put(0x1500b8,tone,'I');machine.put(0x150000+weight_offset,256,'H');machine.run(serializer,0x140000,0x141000)
            serial.append(bytes(machine.u.mem_read(0x180000,PARAMETERS)))
        native_changes=[i for i,(a,b) in enumerate(zip(*serial[:2])) if a!=b]
        p=(ctypes.c_ubyte*PARAMETERS).from_buffer_copy(serial[0])
        assert fn(out,p,PARAMETERS,s,SAMPLES,vector,229,1024)==1
        assert bytes(out)[:PARAMETERS]==serial[1]
        p=(ctypes.c_ubyte*PARAMETERS).from_buffer_copy(serial[2])
        assert fn(out,p,PARAMETERS,s,SAMPLES,vector,229,1024)==1
        assert bytes(out)[0x248:0x25a]==serial[1][0x248:0x25a]
        assert bytes(out)[0x1e8:0x1fc]==serial[1][0x1e8:0x1fc]
        arm_cases=0;curve_samples=0;driver_words=0;nlg_words=0
        for v in d['vectors']:
            z.u.mem_write(0x140000,bytes(0x200));z.put(0x140098,0x150000);z.put(0x140050,0x180000)
            z.put(0x150031,3,'B');z.put(0x150032,192,'h');z.put(0x150034,int(v['ratio']*192),'h')
            z.run(0x4131b3a0,0x140000)
            raw=struct.pack('<229H',*v['values']);vector=(ctypes.c_uint16*229)(*v['values'])
            for off in OFFSETS:assert bytes(z.u.mem_read(0x180000+off,458))==raw;curve_samples+=229
            for gain in (0,1,512,1024,4095,32767,65535):
                assert fn(out,p,PARAMETERS,s,SAMPLES,vector,229,gain)==1
                c.u.mem_write(0x180000,bytes(p));c.u.mem_write(0x182000,bytes(s));c.u.mem_write(0x186000,raw)
                c.u.mem_write(0x190000,b'\xa5'*(SIZE+32))
                assert c.run(entry,0x190010,0x180000,PARAMETERS,0x182000,SAMPLES,0x186000,229,gain)==1
                assert bytes(c.u.mem_read(0x190010,SIZE))==bytes(out)
                assert c.u.mem_read(0x190000,16)==b'\xa5'*16 and c.u.mem_read(0x190010+SIZE,16)==b'\xa5'*16
                arm_cases+=1
            # Real C2.01 constructors retain pointers into the owned candidate.
            source=0x190010+PARAMETERS
            c.u.mem_write(0x1a0000,bytes(0x600));c.run(0x40e625cc,source,0x1a0000)
            c.put(0x120008,0x130000)
            for bank,(off,register) in enumerate(zip(OFFSETS,(0x4210,0x43dc,0x45b0,0x477c,0x4950,0x4b1c))):
                ptr=c.get(0x1a0458+8*bank);assert ptr==source+off
                c.run(0x40c11bf8,0x120000,bank%2,bank//2,ptr)
                words=[v['values'][i]|(v['values'][i+1]<<16)for i in range(0,228,2)]+[v['values'][228]]
                assert list(struct.unpack('<115I',c.u.mem_read(0x130000+register,460)))==words
                driver_words+=115
            ptr=c.get(0x1a0488);assert ptr==source+0x16a2
            assert bytes(c.u.mem_read(ptr,458))==nlg;c.run(0x40c11cac,0x120000,ptr)
            nlg_values=struct.unpack('<229H',nlg)
            words=[(nlg_values[i]&4095)|((nlg_values[i+1]&4095)<<16)for i in range(0,228,2)]+[nlg_values[228]&4095]
            assert list(struct.unpack('<115I',c.u.mem_read(0x134cf0,460)))==words;nlg_words+=115
            c.u.mem_write(0x1b0000,bytes(0x480));c.u.mem_write(0x1b1000,bytes(0x600))
            c.put(0x1b0400,0x190010);c.run(0x40e60b5c,0x1b0000,0x1b1000)
            assert c.get(0x1b1340)==0x190010+0x248
            c.run(0x40c11004,0x120000,c.get(0x1b1340))
            coefficients=struct.unpack('<9H',bytes(out)[0x248:0x25a])
            words=[(coefficients[i]&4095)|((coefficients[i+1]&4095)<<16)for i in range(0,8,2)]+[coefficients[8]&4095]
            assert list(struct.unpack('<5I',c.u.mem_read(0x131664,20)))==words
        result={'passed':True,'firmware_sha256':PINS,'m1_equal_cases':m1_cases,'m2_original_cases':65536,
                'arm_candidate_cases':arm_cases,'original_curve_samples':curve_samples,'channel_driver_words':driver_words,
                'nlg_driver_words':nlg_words,'complete_original_serializers':3,
                'complete_calibration_getters':8,'calibration_sha256':calibration_sha,
                'calibration_pair_s16':list(struct.unpack('<19h',calibration_pair)),
                'native_serializer_changed_offsets':[hex(i)for i in native_changes],
                'zr_m1_rows':list(struct.unpack('<45h',zr_spaces)),
                'zr_m2_rows':list(struct.unpack('<36h',z.u.mem_read(0xa02a1f4fc,72))),
                'nlg_sha256':hashlib.sha256(nlg).hexdigest(),'candidate_elf_sha256':hashlib.sha256(elf).hexdigest(),
                'compiler':subprocess.check_output([clang,'--version'],text=True).strip(),
                'linker':subprocess.check_output([linker,'--version'],text=True).strip(),
                'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in
                    ('src/platform/z63_c201/color_transplant.c','src/platform/z63_c201/color_transplant.h','src/memory.c',
                     'host/check_zr_color_transplant.py','host/color_transplant.py','host/log3g10_reference.json')},
                'regions':{'zr':[z.region(a,n)for a,n in ((0x41311340,0x8e4),(0x41311dbc,0x864),(0x4130e7d8,0xfc),(0x4131b3a0,0x180),(0x4114c2b8,64),(0x4136aacc,120),(0x412490c0,0xd4))],
                           'z63':[c.region(a,n)for a,n in ((0x4111cd60,0x720),(0x4111d618,0x934),(0x40c11004,80),(0x40c11bf8,172),(0x40e625cc,0x208),(0x40f4638c,64),(0x4117588c,112),(0x4104afcc,0xe8))]},
                'native_recording_hook':False,'pixel_basis_proved':False,'recording_qualified':False}
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
        (output/'color-transplant.elf').write_bytes(elf)
        (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--z63',required=True);p.add_argument('--zr',required=True)
    p.add_argument('--zr-calibration',required=True)
    p.add_argument('--clang',required=True);p.add_argument('--linker',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(verify(a.z63,a.zr,a.clang,a.linker,a.output,a.zr_calibration),indent=2))
