"""Execute the linked activation code with explicit file/mapping substitutes.

Actual C/ARM transactions operate on shared executable/writable RAM aliases.
Native MMU queries and filesystem calls are supplied fixtures. Full-system
tests separately exercise the original kernel mappings and card backend.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'host'))
from host.check_zr_color_transplant import Original
from z63_activation import alias,CONTROL_RAM,CONTROL
from unicorn import UC_HOOK_CODE,UC_PROT_ALL
import unicorn.arm64_const as arm


def verify(main,build,output):
    build=Path(build);r=json.loads((build/'probe.json').read_text());image=(build/'probe.eg.bin').read_bytes()
    if hashlib.sha256(image).hexdigest()!=r['candidate_sha256']:raise ValueError('candidate differs')
    if r.get('activation',{}).get('format')!=2:raise ValueError('immutable RAM-record build required')
    m=Original(main,'z63');u=m.u;u.mem_write(0x40160000,image[:-2]);symbols=r['symbols']
    count=m.get(symbols['fx_z63_activation_count'],'I')
    rows=[tuple(m.get(symbols['fx_z63_activation_words']+i*12+j*4,'I') for j in range(3)) for i in range(count)]
    buffers=[]
    for page in sorted({site&~4095 for site,_,_ in rows}|{CONTROL&~4095}):
        data=image[page-0x40160000:page-0x40160000+4096]
        buffer=ctypes.create_string_buffer(data,4096);buffers.append(buffer)
        u.mem_unmap(page,4096);u.mem_map_ptr(page,4096,UC_PROT_ALL,ctypes.addressof(buffer))
        u.mem_map_ptr(alias(page),4096,UC_PROT_ALL,ctypes.addressof(buffer))
    state,files,profile,closing,window=0x110000,0x111000,0x112000,0x113000,0x113008
    open_pc,read_pc,close_pc=0x114000,0x114004,0x114008
    mmu=0xa04edb048
    behavior={};trace=[]
    def callback(cpu,pc,size,data):
        regs=[cpu.reg_read(getattr(arm,'UC_ARM64_REG_X'+str(i))) for i in range(5)]
        if pc==symbols.get('exchange'):
            behavior['exchanges']+=1
            if behavior.get('steal')==behavior['exchanges']:
                site=m.get(regs[1],'I');m.put(alias(site),99,'I')
            return
        result=0
        if pc==open_pc:
            behavior['opens']+=1;result=0x80000010 if behavior.get('missing') else 7
        elif pc==read_pc:
            behavior['reads']+=1
            payload=behavior['payload'];at=behavior['at'];n=min(regs[2],7,len(payload)-at)
            if behavior.get('read_error'):result=1;n=0
            if n:cpu.mem_write(regs[1],payload[at:at+n])
            m.put(regs[3],regs[2]+1 if behavior.get('overflow') else n,'I');behavior['at']+=n
            if behavior.get('shutdown_read'):m.put(closing,1,'I')
            if behavior.get('update_read'):m.put(CONTROL_RAM,2,'I')
        elif pc==close_pc:
            behavior['closes']+=1;result=int(behavior.get('close_error',False))
        elif pc in (0x401751dc,0x40175248):
            behavior['queries']+=1;va=regs[1]
            expected=alias(va) if va<0x100000000 else va
            if pc==0x401751dc:
                m.put(regs[2],expected+(4096 if behavior.get('wrong_mapping') else 0))
            else:
                attributes=2 if va<0x100000000 else int(behavior.get('readonly_alias',False))
                m.put(regs[2],attributes,'I')
        else:raise AssertionError(hex(pc))
        cpu.reg_write(arm.UC_ARM64_REG_X0,result)
        cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))
    for pc in (open_pc,read_pc,close_pc,0x401751dc,0x40175248,symbols['exchange']):
        u.hook_add(UC_HOOK_CODE,callback,begin=pc,end=pc)
    payload=(build/'FX63ARM.BIN').read_bytes()
    def reset(**changes):
        behavior.clear();behavior.update(payload=payload,at=0,opens=0,reads=0,closes=0,queries=0,exchanges=0);behavior.update(changes)
        for site,old,new in rows:m.put(alias(site),old,'I');u.ctl_remove_cache(site,site+4)
        u.mem_write(CONTROL_RAM,bytes(32));u.mem_write(state,bytes(0x5000))
        m.put(profile,open_pc);m.put(profile+8,read_pc);m.put(profile+24,close_pc);m.put(profile+64,0x80000010,'I')
        m.put(files,profile);m.put(files+8,closing);m.put(files+16,window)
        m.put(mmu,0xa04000000);m.put(mmu+0x38,1,'B')
        for i in range(3):m.put(mmu+0x40+i*8,0xa04001000+i*4096)
        for at in (0xa035d9f00,0xa035d9fb8):m.put(at,0,'I')
        m.run(symbols['fx_z63_activation_init'],state)
    reset()
    assert m.run(symbols['fx_z63_activation_shell_enter'])==3 and m.get(CONTROL_RAM,'I')==3
    assert m.run(symbols['fx_z63_activation_shell_enter'])==0
    m.run(symbols['fx_z63_activation_shell_leave'],3);assert m.get(CONTROL_RAM,'I')==0
    for value,lease in ((1,1),(2,0),(3,0),(0xffffffff,0)):
        m.put(CONTROL_RAM,value,'I');assert m.run(symbols['fx_z63_activation_shell_enter'])==lease
        m.run(symbols['fx_z63_activation_shell_leave'],lease);assert m.get(CONTROL_RAM,'I')==value
    refusals=[]
    cases=(('missing',dict(missing=True),12),('short',dict(payload=payload[:-1]),10),
           ('long',dict(payload=payload+b'x'),10),('wrong-build',dict(payload=payload[:8]+bytes(32)+payload[40:]),10),
           ('corrupt',dict(payload=payload[:63]+bytes([payload[63]^1])),10),
           ('read-error',dict(read_error=True),8),('count-overflow',dict(overflow=True),10),
           ('close-error',dict(close_error=True),11),('shutdown-during-read',dict(shutdown_read=True),2),
           ('update-during-read',dict(update_read=True),2),('wrong-mapping',dict(wrong_mapping=True),3),
           ('readonly-alias',dict(readonly_alias=True),3))
    for name,values,expected in cases:
        reset(**values);actual=m.run(symbols['fx_z63_activation_admit'],state,files)
        assert actual==expected,(name,actual,expected)
        assert m.get(CONTROL_RAM,'I')==(2 if values.get('update_read') else 0)
        assert all(m.get(alias(site),'I')==old for site,old,new in rows)
        assert behavior['opens']==1 and behavior['closes']==(0 if values.get('missing') else 1)
        refusals.append(dict(case=name,result=actual,feature_words_unchanged=True,file_closed=bool(behavior['closes'])))
    reset();m.put(closing,1,'I')
    assert m.run(symbols['fx_z63_activation_admit'],state,files)==2 and not behavior['opens']
    reset();assert m.run(symbols['fx_z63_activation_admit'],state,files)==0
    assert m.get(CONTROL_RAM,'I')==1 and m.get(state,'I')==1
    assert all(m.get(alias(site),'I')==old for site,old,new in rows)
    assert m.run(symbols['fx_z63_activation_install'],state)==0
    assert all(m.get(alias(site),'I')==new and m.get(site,'I')==new for site,old,new in rows)
    assert m.get(state+8)==(1<<count)-1
    m.run(symbols['fx_z63_activation_running'],state,0x123456789)
    assert m.get(CONTROL_RAM+4,'I')==1 and m.get(CONTROL_RAM+8)==0x123456789
    # Retain code/control while resetting state/data. Require both actual
    # MAIN wake decisions, not merely a retained patch word.
    wake=[]
    for first,second,committed in ((0,0,1),(1,0,1),(0,1,1),(1,1,3),(1,1,1)):
        m.put(0xa035d9f00,first,'I');m.put(0xa035d9fb8,second,'I');m.put(CONTROL_RAM+4,committed,'I')
        m.run(symbols['fx_z63_activation_init'],state)
        expected=int(first==second==committed==1);assert m.get(state+16,'I')==expected
        wake.append(dict(startup=first,handoff=second,commit=committed,resume=expected))
    behavior.update(at=0,exchanges=0)
    assert m.run(symbols['fx_z63_activation_admit'],state,files)==0
    assert m.run(symbols['fx_z63_activation_install'],state)==0 and not behavior['exchanges']
    m.run(symbols['fx_z63_activation_retire'],state,1)
    assert m.get(CONTROL_RAM+4,'I')==3
    assert m.run(symbols['fx_z63_activation_restore'],state)==0
    assert m.get(CONTROL_RAM,'I')==1 and not m.get(state+8)
    assert all(m.get(alias(site),'I')==old for site,old,new in rows)
    m.run(symbols['fx_z63_activation_cleaned'],state,0)
    assert m.get(CONTROL_RAM+4,'I')==1
    reset();assert m.run(symbols['fx_z63_activation_admit'],state,files)==0
    behavior['steal']=2
    assert m.run(symbols['fx_z63_activation_install'],state)==10
    assert m.get(alias(rows[1][0]),'I')==99 and not m.get(state+8)
    assert m.get(CONTROL_RAM,'I')==1 and m.get(CONTROL_RAM+4,'I')==3
    reset();assert m.run(symbols['fx_z63_activation_admit'],state,files)==0
    assert m.run(symbols['fx_z63_activation_install'],state)==0
    m.put(alias(rows[0][0]),99,'I')
    assert m.run(symbols['fx_z63_activation_restore'],state)==10 and m.get(state+8)==1
    assert m.get(alias(rows[0][0]),'I')==99
    for manual in (0,1):
        reset();assert m.run(symbols['fx_z63_activation_admit'],state,files)==0
        assert m.run(symbols['fx_z63_activation_install'],state)==0
        m.run(symbols['fx_z63_activation_retire'],state,0 if manual else 1)
        m.run(symbols['fx_z63_activation_running'],state,0x1234)
        assert m.get(state,'I')==3 and m.get(CONTROL_RAM+4,'I')==(2 if manual else 3)
    result=dict(passed=True,candidate_sha256=r['candidate_sha256'],ram_records=count,
        input_refusals=refusals,wake_decisions=wake,shared_alias_install_and_restore=True,
        rollback_preserves_competing_writer=True,uncertain_restoration_retains_ownership=True,
        update_interlock_retained_after_restore=True,shutdown_before_io_refused=True,
        late_worker_commit_cannot_override_retirement=True,
        shell_initialization_excludes_update_and_releases_only_its_lease=True,
        scope=__doc__,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),physical_camera_tested=False)
    p=Path(output)
    if p.exists():raise ValueError('new output required')
    p.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('main','build','output'):p.add_argument('--'+key,required=True)
    print(json.dumps(verify(**vars(p.parse_args())),indent=2))
