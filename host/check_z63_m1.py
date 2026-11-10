"""Execute C2.01 M1 producers and transport offline. No pixel engine."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from host.mipu_color_reference import matrix_product,m1_registers
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3,UC_ARM64_REG_SP,UC_ARM64_REG_LR,UC_ARM64_REG_PC,UC_ARM64_REG_CPACR_EL1

SHA='236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87'


def verify(application):
    blob=Path(application).read_bytes()
    if hashlib.sha256(blob).hexdigest()!=SHA:raise ValueError('C2.01 MAIN identity differs')
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
    u.mem_map(0x40160000,(len(blob)+4095)&~4095);u.mem_write(0x40160000,blob)
    u.mem_map(0xa02800000,0x2800000);u.mem_write(0xa02808000,blob[0x5095000:0x546e028])
    u.mem_map(0x100000,0x100000);u.reg_write(UC_ARM64_REG_CPACR_EL1,3<<20)
    def put(a,v,fmt='Q'):u.mem_write(a,struct.pack('<'+fmt,v))
    def get(a,fmt='Q'):return struct.unpack('<'+fmt,u.mem_read(a,struct.calcsize('<'+fmt)))[0]
    def run(pc,args,end=0x1ffff0):
        u.reg_write(UC_ARM64_REG_SP,0x1fe000);u.reg_write(UC_ARM64_REG_LR,end)
        for reg,value in zip((UC_ARM64_REG_X0,UC_ARM64_REG_X1,UC_ARM64_REG_X2,UC_ARM64_REG_X3),args):u.reg_write(reg,value)
        u.emu_start(pc,end,count=1000000)
        if u.reg_read(UC_ARM64_REG_PC)!=end:raise AssertionError('instruction bound reached')
    spans=[(0x4111cd60,0x720),(0x41135b2c,0x330),(0x40c10d94,88),(0x40e60b5c,0x460),(0x4111a7f4,0xf8),(0x4111c770,0xe4),(0x40e6d070,0x104)]
    identities=[{'address':hex(a),'bytes':n,'sha256':hashlib.sha256(blob[a-0x40160000:a-0x40160000+n]).hexdigest()} for a,n in spans]
    rng=random.Random(0x201)
    cases=[]
    for limit in (1024,4095,32767):
        for _ in range(100):
            a=[rng.randint(-limit,limit) for _ in range(9)];b=[rng.randint(-limit,limit) for _ in range(9)]
            for divisor in (0,1,2,1024,32768):cases.append((a,b,divisor))
    for a,b,d in cases:
        u.mem_write(0x110000,struct.pack('<9h',*a));u.mem_write(0x110100,struct.pack('<9h',*b))
        u.mem_write(0x1101f0,b'\xa5'*50)
        run(0x41135b2c,(0x110000,0x110100,0x110200,d))
        assert list(struct.unpack('<9h',u.mem_read(0x110200,18)))==matrix_product(a,b,d)
        assert u.mem_read(0x1101f0,16)==b'\xa5'*16 and u.mem_read(0x110212,16)==b'\xa5'*16
    driver_cases=0
    put(0x120008,0x130000)
    for value in range(65536):
        block=struct.pack('<10H',value,*[(value+k*8191)&65535 for k in range(9)])
        u.mem_write(0x110000,block);u.mem_write(0x1315d0,b'\xa5'*48)
        run(0x40c10d94,(0x120000,0x110000))
        assert list(struct.unpack('<6I',u.mem_read(0x1315dc,24)))==m1_registers(block)
        assert u.mem_read(0x1315d0,12)==b'\xa5'*12 and u.mem_read(0x1315f4,12)==b'\xa5'*12
        driver_cases+=1
    filters=list(struct.unpack('<99h',u.mem_read(0xa029e8d40,198)))
    spaces=list(struct.unpack('<36h',u.mem_read(0xa029e8e06,72)))
    scale=list(struct.unpack('<7h',u.mem_read(0xa029e8e4e,14)))
    producer_cases=0
    # Complete producer. Tone zero isolates the established Q10/Q15 joins.
    for row in range(11):
        for weight in (0,26,51,77,102,128,154,179,205,230,256):
            for space in range(4):
                for calibration in ([16384,0,0,0,16384,0,0,0,16384],[18000,-1000,500,700,16000,-400,-200,300,17000]):
                    u.mem_write(0x140000,bytes(0x200));u.mem_write(0x150000,bytes(0x200))
                    put(0x140000,0x160000);put(0x140040,0x150000);put(0x1400a0,0x170000)
                    u.mem_write(0x160000,struct.pack('<10h',1,*calibration))
                    put(0x150106,1,'B');put(0x15003c,127+row,'I');put(0x150126,weight,'H');put(0x1500a8,space,'I')
                    u.mem_write(0x170000,b'\xa5'*64)
                    run(0x4111cd60,(0x140000,))
                    f=filters[row*9:row*9+9]
                    def rounded(v):return (1 if v>=0 else -1)*((abs(v)+128)//256)
                    blended=[rounded(2*(weight*v+(256-weight)*(1024 if k%4==0 else 0))) for k,v in enumerate(f)]
                    expected=matrix_product(matrix_product(spaces[space*9:space*9+9],blended,1024),calibration,32768)
                    assert get(0x170010,'H')==0
                    assert list(struct.unpack('<9h',u.mem_read(0x170012,18)))==expected,(row,weight,space,list(struct.unpack('<9h',u.mem_read(0x170012,18))),expected,spaces[:9])
                    assert u.mem_read(0x170000,16)==b'\xa5'*16 and u.mem_read(0x170024,28)==b'\xa5'*28
                    producer_cases+=1
    tone_cases=0
    for tone in (-1,1,2,3):
        for coordinate in (-1,0,1,2,3,4,5,6,7):
            for row in range(11):
                for weight in (0,128,256):
                    u.mem_write(0x140000,bytes(0x200));u.mem_write(0x150000,bytes(0x200))
                    put(0x140000,0x160000);put(0x140040,0x150000);put(0x1400a0,0x170000)
                    calibration=[18000,-1000,500,700,16000,-400,-200,300,17000]
                    u.mem_write(0x160000,struct.pack('<10h',1,*calibration))
                    put(0x150106,1,'B');put(0x15003c,127+row,'I');put(0x150126,weight,'H')
                    put(0x1500b8,tone,'i');put(0x1500bc,coordinate,'i')
                    run(0x4111cd60,(0x140000,))
                    f=filters[row*9:row*9+9]
                    blended=[rounded(2*(weight*v+(256-weight)*(1024 if k%4==0 else 0))) for k,v in enumerate(f)]
                    color=spaces[max(0,min(3,tone+1))*9:max(0,min(3,tone+1))*9+9]
                    divisor=1<<20
                    intermediate=[]
                    for r in range(3):
                        for c in range(3):
                            value=sum(color[r*3+k]*blended[k*3+c] for k in range(3))*scale[max(0,min(6,coordinate))]
                            intermediate.append((1 if value>=0 else -1)*((abs(value)+divisor//2)//divisor))
                    expected=matrix_product(intermediate,calibration,32768)
                    assert list(struct.unpack('<9h',u.mem_read(0x170012,18)))==expected,(tone,coordinate,row,weight)
                    tone_cases+=1
    # Complete ordinary serializer, then complete dynamic builder and M1 driver.
    # Inputs are synthetic prepared data, not a camera-mode acquisition.
    u.mem_write(0x140000,bytes(0x100));u.mem_write(0x150000,bytes(0x200))
    u.mem_write(0x160000,bytes(0x200));u.mem_write(0x170000,bytes(0x1000))
    u.mem_write(0x180000,bytes(0x1000));u.mem_write(0x190000,bytes(0x1000))
    put(0x140000,0x160000);put(0x140010,0x150000);put(0x140018,0x170000)
    put(0x141000,0x160100);put(0x141008,0x180000);put(0x141010,0x190000)
    calibration=[16384,0,0,0,16384,0,0,0,16384]
    u.mem_write(0x160000,struct.pack('<10h',1,*calibration))
    put(0x1500b8,1,'i');put(0x150126,256,'H')
    run(0x4111a7f4,(0x140000,0x141000))
    serialized=bytes(u.mem_read(0x1801e8,20))
    assert list(struct.unpack('<10h',serialized))==[0,1024,0,0,0,1024,0,0,0,1024]
    u.mem_write(0x1a0000,bytes(0x480));u.mem_write(0x1a1000,bytes(0x600))
    put(0x1a0400,0x180000)
    run(0x40e60b5c,(0x1a0000,0x1a1000))
    serialized_pointer=get(0x1a1318)
    assert serialized_pointer==0x1801e8
    put(0x120008,0x130000)
    run(0x40c10d94,(0x120000,serialized_pointer))
    assert list(struct.unpack('<6I',u.mem_read(0x1315dc,24)))==m1_registers(serialized)
    # Complete dynamic builder with supplied roots, including the movie and alternate roots.
    routes=[]
    for slot,offset in ((0x3f8,0x3ac),(0x400,0x1e8),(0x420,0x1e8),(0x428,0x24)):
        u.mem_write(0x180000,bytes(0x480));u.mem_write(0x181000,bytes(0x600))
        put(0x180000+slot,0x190000)
        run(0x40e60b5c,(0x180000,0x181000))
        result=get(0x181318)
        routes.append({'request_slot':hex(slot),'source_offset':hex(result-0x190000)})
        assert result==0x190000+offset,(slot,hex(result))
    # An empty builder input does not itself clear a retained M1 pointer.
    u.mem_write(0x180000,bytes(0x480));put(0x181318,0x1abcdef0)
    run(0x40e60b5c,(0x180000,0x181000))
    assert get(0x181318)==0x1abcdef0
    movie_prefix_cases=0
    for mode in (6,7):
        u.mem_write(0x180000,bytes(0x1000));u.mem_write(0x181000,bytes(0x480));u.mem_write(0x182000,bytes(0x3000))
        put(0x180010,mode,'I');put(0x180054,1,'B');put(0x180055,1,'B');put(0x180a58,0x182000)
        run(0x40e6d070,(0,0x180000,0x190000,0x181000),0x40e6d174)
        assert get(0x1813f8)==0 and get(0x181400)==0x191bd8
        movie_prefix_cases+=1
    return {'firmware_sha256':SHA,'source_spans':identities,'matrix_cases':len(cases),'driver_cases':driver_cases,'producer_cases':producer_cases,'tone_cases':tone_cases,'filter_rows':[filters[k:k+9] for k in range(0,99,9)],'space_rows':[spaces[k:k+9] for k in range(0,36,9)],'tone_scale_values':scale,'dynamic_routes':routes,'ordinary_serializer_to_driver_cases':1,'movie_assembler_prefix_cases':movie_prefix_cases,'empty_builder_retains_pointer':True,'pixel_order_proved':False,'recording_qualified':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('application');p.add_argument('--output',type=Path);a=p.parse_args()
    result=verify(a.application);text=json.dumps(result,indent=2)+'\n'
    if a.output:a.output.write_text(text)
    print(text)
