"""Linked H.265 recording snapshots with original copy/clear/metadata code.

The original kernel mutex is supplied. Shared capture storage and native work
states are explicit fixtures; this does not execute the scheduler or a camera.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'host'))
from host.check_zr_color_transplant import Original
from z63_activation import CONTROL_RAM
from unicorn import UC_HOOK_CODE
import unicorn.arm64_const as arm


def verify(main,build,output):
    build=Path(build);image=(build/'probe.eg.bin').read_bytes();r=json.loads((build/'probe.json').read_text());symbols=r['symbols']
    if hashlib.sha256(image).hexdigest()!=r['candidate_sha256']:raise ValueError('candidate differs')
    m=Original(main,'z63');u=m.u;u.mem_write(0x40160000,image[:-2])
    u.mem_map(0xa01000000,0x20000);u.mem_map(CONTROL_RAM&~4095,4096)
    m.put(CONTROL_RAM,1,'I');root=0xa01000000;m.put(0xa02912e60,root)
    m.put(root+64,0x465a634d,'I');m.put(root+68,1,'I');m.put(root+76,1,'I')
    video_meta=struct.unpack_from('<9I',image,symbols['fx_z63_video_layout']-0x40160000)
    join=struct.unpack_from('<10I',image,symbols['fx_z63_late_join_layout']-0x40160000)
    h265=struct.unpack_from('<9I',image,symbols['fx_z63_h265_layout']-0x40160000)
    layout=struct.unpack_from('<10I',image,symbols['fx_z63_recording_layout']-0x40160000)
    video=root+video_meta[2];record=video+layout[2];policy=video+h265[2]
    count=m.get(symbols['fx_z63_activation_count'],'I')
    for i in range(count):
        site,old,new=struct.unpack_from('<III',image,symbols['fx_z63_activation_words']-0x40160000+i*12)
        assert m.get(site,'I')==old; m.put(site,new,'I')
    def callee(site):
        word=struct.unpack_from('<I',m.blob,site-0x40160000)[0];assert word>>26==0x25
        delta=word&0x3ffffff
        if delta&(1<<25):delta-=1<<26
        return site+delta*4
    copy,clear=callee(0x4075604c),callee(0x40758158)
    lock=[False];lock_failure=[False];calls={'copy':0,'clear':0,'metadata':0}
    def observed(cpu,pc,size,data):
        if pc==0x40d32f74:
            assert not lock[0];lock[0]=not lock_failure[0];value=int(lock[0])
        elif pc==0x40d32f60:
            assert lock[0];lock[0]=False;value=0
        else:
            calls[{copy:'copy',clear:'clear',symbols['fx_z63_video_h265_metadata_original']:'metadata'}[pc]]+=1
            return
        cpu.reg_write(arm.UC_ARM64_REG_X0,value);cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))
    for pc in (0x40d32f74,0x40d32f60,copy,clear,symbols['fx_z63_video_h265_metadata_original']):
        u.hook_add(UC_HOOK_CODE,observed,begin=pc,end=pc)
    source,destination,meta_out,rate_out=0xa03d81340,0xa048bb3b8,0xa05000020,0xa05001020
    def active(value):
        for off in join[4:7]:m.put(video+off+join[8]+4,value,'I')
    def call(pc,*args,stop=0x1ffff0):
        u.reg_write(arm.UC_ARM64_REG_SP,0x1fe000);u.reg_write(arm.UC_ARM64_REG_LR,stop)
        for i in range(8):u.reg_write(arm.UC_ARM64_REG_X0+i,args[i] if i<len(args) else 0)
        u.emu_start(pc,stop,count=12000000)
        assert u.reg_read(arm.UC_ARM64_REG_PC)==stop,hex(u.reg_read(arm.UC_ARM64_REG_PC))
        assert not lock[0]
        return u.reg_read(arm.UC_ARM64_REG_X0)
    def reset(tier,type):
        u.mem_write(video,bytes(4096));m.put(video+join[2],1,'I')
        for off in join[4:7]:m.put(video+off+join[7],3,'I')
        active(1)
        m.put(policy+h265[4],tier,'I')
        u.mem_write(source,bytes(0x110));m.put(source+0x20,type,'I')
        m.put(0xa048bb3b0,source);m.put(0xa048bb044,0,'I');m.put(0xa03324ce0,0,'I');m.put(0xa03324dc8,0,'I')
        m.put(0xa03d42100,2,'I');m.put(0xa03d42108,7,'I');m.put(0xa03f0eee0,type,'I')
        u.mem_write(meta_out-16,b'\xa5'*288);u.mem_write(rate_out-16,b'\xa5'*80)
    cases=[]
    for type in (2,3):
        for tier in range(5):
            for later in range(5):
                reset(tier,type)
                assert call(symbols['fx_z63_video_native_pending'])==1
                before=calls['copy']
                call(0x4075604c,destination,source,0x110,stop=0x40756050)
                assert calls['copy']==before+1 and bytes(u.mem_read(destination,0x110))==bytes(u.mem_read(source,0x110))
                snapshot=m.get(record)
                assert snapshot and (snapshot>>1)&7==tier
                m.put(policy+h265[4],later,'I') # Constructed late-global change.
                index=49 if type==3 else 31
                row=0x42ac02fc+36*index
                # Pick a matching native H.265 depth/width row independently.
                for index in range(61):
                    row=0x42ac02fc+36*index;codec,fmt=m.get(row,'I'),m.get(row+4,'I')
                    if codec==1 and fmt&65535==(10 if type==3 else 8) and fmt>>16==3840:break
                original_row=bytes(u.mem_read(row,36))
                call(symbols['fx_z63_h265_copy'],rate_out,row,36,index,0x402fd5b0)
                expected=bytearray(original_row);rate=struct.unpack_from('<I',expected,28)[0]
                struct.pack_into('<I',expected,28,rate*(100,60,45,30,20)[tier]//100)
                assert bytes(u.mem_read(rate_out,36))==expected
                before=calls['metadata']
                assert call(0x40707038,destination,meta_out)==1
                assert calls['metadata']==before+1 and m.get(meta_out+0xa8,'I')==(1 if tier==0 else 2)
                assert bytes(u.mem_read(meta_out-16,16))==b'\xa5'*16 and bytes(u.mem_read(meta_out+256,16))==b'\xa5'*16
                # A repeated/coalesced copy does not capture the later global.
                call(0x4075604c,destination,source,0x110,stop=0x40756050)
                assert m.get(record)==snapshot
                active(0);assert call(symbols['fx_z63_video_quiescent'],video)==0 and m.get(record)==snapshot
                assert call(symbols['fx_z63_video_native_pending'])==1
                active(1);m.put(0xa048bb044,2,'I')
                before=calls['clear']
                call(0x40758158,0xa048bb3b0,0,0x72b0,stop=0x4075815c)
                assert calls['clear']==before+1 and not any(u.mem_read(0xa048bb3b0,0x72b0))
                assert m.get(record+layout[5],'I')==snapshot>>32
                assert call(symbols['fx_z63_video_quiescent'],video)==0 and m.get(record)==snapshot
                active(0);m.put(0xa048bb044,0,'I');call(symbols['fx_z63_video_quiescent'],video)
                assert m.get(record)==0 and m.get(record+layout[9],'I')==1,dict(type=type,tier=tier,later=later,
                    record=[m.get(record+i*4,'I') for i in range(8)],
                    counters=[m.get(video+off+join[8]+i*4,'I') for off in join[4:7] for i in range(2)],
                    native=[m.get(a,'I') for a in (0xa048bb044,0xa03324ce0,0xa03324dc8,0xa03d42100,0xa03d42108)])
                assert call(symbols['fx_z63_video_native_pending'])==0
                cases.append(dict(type=type,tier=tier,later_global=later,rate_preserved=True,late_metadata_preserved=True))
    failures=[]
    for fault in ('untracked-copy','wrong-copy-size','unknown-format','copy-lock-failure',
                  'wrong-clear-value','wrong-clear-span','clear-lock-failure'):
        reset(4,3);lock_failure[0]=False
        if fault=='untracked-copy':active(0)
        if fault=='unknown-format':m.put(source+0x20,0,'I')
        if fault=='copy-lock-failure':lock_failure[0]=True
        before=calls['copy'];size=0x100 if fault=='wrong-copy-size' else 0x110
        call(0x4075604c,destination,source,size,stop=0x40756050)
        assert calls['copy']==before+1
        assert bytes(u.mem_read(destination,size))==bytes(u.mem_read(source,size))
        lock_failure[0]=False
        if 'clear' in fault:
            snapshot=m.get(record);assert snapshot
            if fault=='clear-lock-failure':lock_failure[0]=True
            before=calls['clear']
            call(0x40758158,0xa048bb3b0,int(fault=='wrong-clear-value'),
                 0x72a0 if fault=='wrong-clear-span' else 0x72b0,stop=0x4075815c)
            assert calls['clear']==before+1 and m.get(record)==snapshot
            lock_failure[0]=False
        active(0)
        assert m.get(record+layout[6],'I')==1
        assert call(symbols['fx_z63_video_quiescent'],video)==0
        assert call(symbols['fx_z63_video_native_pending'])==0
        for off in join[4:7]:assert m.get(video+off+join[9],'I')==1
        failures.append(dict(case=fault,original_called_once=True,ownership_retained=True,all_video_admission_faulted=True))
    result=dict(passed=True,candidate_sha256=r['candidate_sha256'],cases=cases,
        failure_cases=failures,
        original_copy_clear_and_metadata_executed=True,duplicate_copy_keeps_snapshot=True,
        idle_without_clear_cannot_retire=True,callback_and_native_work_fence_retirement=True,
        verified_native_work_defers_module_cleanup_deadline=True,fault_cannot_renew_cleanup_deadline=True,
        call_counts=calls,scope=__doc__,physical_camera_tested=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    out=Path(output)
    if out.exists():raise ValueError('new output required')
    out.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('main','build','output'):p.add_argument('--'+key,required=True)
    print(json.dumps(verify(**vars(p.parse_args())),indent=2))
