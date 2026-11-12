"""Original task-query layout and linked late-join rejection controls.

Kernel query execution uses supplied TCBs and an uncontended kernel lock.
Linked join controls supply mutex/query replies and inject races. No real
scheduler, cross-core timing or physical camera is exercised.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.check_zr_color_transplant import Original
from unicorn import UC_HOOK_CODE
import unicorn.arm64_const as arm


def query_contract(main):
    m=Original(main,'z63');u=m.u
    tcb,ini,scheduler,flags,context,info=range(0x160000,0x166000,0x1000)
    m.put(0xa02bd6f50,1,'I');m.put(0xa04d154b8,tcb)
    m.put(tcb+0x10,ini);m.put(tcb+0x20,scheduler)
    m.put(0xa04d264c0,flags);m.put(tcb+0x60,flags+6*32)
    u.reg_write(arm.UC_ARM64_REG_TPIDR_EL1,context)
    cases=[]
    for state,expected in ((0x2a,(4,8,7)),(0x2e,(12,8,7)),(1,(1,0,0)),(0,(16,0,0))):
        u.mem_write(info,bytes(80));m.put(tcb+0x18,state,'B');m.put(scheduler,tcb)
        u.reg_write(arm.UC_ARM64_REG_PSTATE,5);m.put(0xa04eef1f8,0,'I')
        assert m.run(0x4018c8cc,1,info)==0
        got=(m.get(info,'I'),m.get(info+12,'I'),m.get(info+16,'I'))
        assert got==expected,(state,got)
        cases.append({'supplied_tcb_state':state,'task_state_wait_reason_object':got})
    for interrupt,depth in ((0x80,0),(0,1)):
        u.reg_write(arm.UC_ARM64_REG_PSTATE,5|interrupt);m.put(context+0x50,depth,'I')
        assert m.run(0x4018c8cc,1,info)&0xffffffff==0xffffffe7
    return {'executed_original_query':True,'cases':cases,'context_refusals':2,
            'query_span':m.region(0x4018c8cc,0x3cc)}


def linked_contract(main,build):
    m=Original(main,'z63');u=m.u;build=Path(build)
    image=(build/'probe.eg.bin').read_bytes();r=json.loads((build/'probe.json').read_text())
    if hashlib.sha256(image).hexdigest()!=r['candidate_sha256']:raise ValueError('candidate differs')
    u.mem_write(0x40160000,image[:-2]);symbols=r['symbols']
    layout=struct.unpack_from('<10I',image,symbols['fx_z63_late_join_layout']-0x40160000)
    assert layout[:2]==(0x464a4e31,1)
    ready,enabled=layout[2:4];policies=layout[4:7];registered,active,fault=layout[7:]
    state=0x180000;mode=['valid'];held=[False];queries=[0];domain=[0]
    objects=(0xa03324b68,0xa048baf98);callbacks=(0x40d22770,0x40755a54);masks=(0x1fff,0xf1ffffff)
    def substitute(cpu,pc,size,data):
        if pc==0x40d32f74:
            held[0]=mode[0]!='lock-failed';result=int(held[0])
        else:
            assert held[0];queries[0]+=1
            ident=cpu.reg_read(arm.UC_ARM64_REG_X0);out=cpu.reg_read(arm.UC_ARM64_REG_X1)
            assert ident==domain[0]+1
            values=[0]*20;values[0]=4;values[3]=8;values[4]=domain[0]+7
            if mode[0]=='running':values[0]=1
            if mode[0]=='suspended':values[0]=12
            if mode[0]=='other-wait':values[3]=4
            if mode[0]=='other-flag':values[4]+=1
            cpu.mem_write(out,struct.pack('<20I',*values));result=-25 if mode[0]=='query-failed' else 0
            object=objects[domain[0]]
            for name,offset,value,fmt in (('changed-id',0,99,'I'),('changed-flag',0x38,99,'I'),
                    ('changed-entry',8,0,'Q'),('changed-callback',0x48,0,'Q'),('changed-mask',0x50,0,'I')):
                if mode[0]==name:m.put(object+offset,value,fmt)
            if mode[0]=='became-busy':m.put(0xa03324ce0,1,'I')
        cpu.reg_write(arm.UC_ARM64_REG_X0,result&0xffffffffffffffff)
        cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))
    for pc in (0x40d32f74,0x4018c8cc):u.hook_add(UC_HOOK_CODE,substitute,begin=pc,end=pc)
    names=('valid','unpublished','not-ready','fault','active','busy','lock-failed',
           'bad-id','bad-flag','bad-entry','bad-callback','bad-mask','running','suspended',
           'other-wait','other-flag','query-failed','changed-id','changed-flag','changed-entry',
           'changed-callback','changed-mask','became-busy')
    results=[]
    for which in (0,1):
        domain[0]=which
        for name in names:
            mode[0]=name;held[0]=False;queries[0]=0;u.mem_write(state,bytes(256))
            m.put(state+ready,int(name!='not-ready'),'I');m.put(state+enabled,int(name!='unpublished'),'I')
            for policy in policies:m.put(state+policy+registered,3^(1<<which),'I')
            if name=='fault':m.put(state+policies[0]+fault,1,'I')
            if name=='active':m.put(state+policies[0]+active+4*which,1,'I')
            for addr in (0xa03324ce0,0xa03324dc8,0xa048bb044,0xa03d42100,0xa03d42108):m.put(addr,0,'I')
            if name=='busy':m.put(0xa03324ce0,1,'I')
            for i,object in enumerate(objects):
                m.put(object,i+1,'I');m.put(object+8,0x40c0025c)
                m.put(object+0x38,i+7,'I');m.put(object+0x48,callbacks[i]);m.put(object+0x50,masks[i],'I')
            for test,offset,value,fmt in (('bad-id',0,0,'I'),('bad-flag',0x38,0,'I'),
                    ('bad-entry',8,0,'Q'),('bad-callback',0x48,0,'Q'),('bad-mask',0x50,0,'I')):
                if name==test:m.put(objects[which]+offset,value,fmt)
            result=m.run(symbols['lock'],state)
            assert result==(0 if name in ('not-ready','lock-failed') else 1)
            expected=3 if name=='valid' else 3^(1<<which)
            assert all(m.get(state+policy+registered,'I')==expected for policy in policies),name
            results.append({'domain':which,'case':name,'query_calls':queries[0],'joined':name=='valid'})
    return {'passed':True,'candidate_sha256':r['candidate_sha256'],'cases':results,
            'scope':'Linked lock/join, with supplied native mutex and task-query responses.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('main','build','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();result={'original_query':query_contract(a.main),'linked_join':linked_contract(a.main,a.build),
                           'physical_camera_tested':False,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
