"""Run stock-first bootstrap and real core initialization with supplied I/O.

Original dispatcher instructions execute. Three original completion consumers,
the dispatch lock, allocator/free and mutex primitives are substitutes. No
hardware boot, native scheduling or physical memory ownership is qualified.
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
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
import unicorn.arm64_const as arm


def verify(main, build, output):
    build=Path(build);image=(build/'probe.eg.bin').read_bytes()
    receipt=json.loads((build/'probe.json').read_text())
    if hashlib.sha256(image).hexdigest()!=receipt['candidate_sha256']:raise ValueError('candidate differs')
    m=Original(main,'z63');u=m.u;u.mem_write(0x40160000,image[:-2])
    if receipt.get('activation'):u.mem_map(0xa17200000,0x30000)
    symbols=receipt['symbols'];guard=int(receipt['guards']['0x40d66ef0'],16)
    slot,old_descriptor=0xa02912e60,0xa028d5590
    fonts_slot,attributes_slot=0xa0305f980,0xa0305f990
    arena=0xa10000000;u.mem_map(arena,0x2000000)
    fonts,attributes=arena,arena+0x1000
    message=0x180000
    core_begin,core_end=receipt['placement']['code_region']
    allocator=0x40d32d00
    consumers=(0x40d6cd84,0x40d6c630,0x40d6a168)
    substitutes=(allocator,0x40d32d40,0x40d32e64,0x40d32f98,0x40d32f60,0x40d32f74,
                 0x40d6efe8,0x40d6efe4,0x40c00204,*consumers)
    progress={}

    def observe(cpu,pc,size,data):
        if pc==guard+0x28:
            progress['stock_returned']=True
            assert progress['consumers']==list(consumers)
            return
        if pc in symbols.values() and core_begin<=pc<core_end:
            assert progress['stock_returned'],('core before stock completion',hex(pc))
            progress['core_entries']+=1
            return
        if pc in consumers:progress['consumers'].append(pc)
        result=1
        if pc==allocator:
            assert progress['stock_returned']
            n=cpu.reg_read(arm.UC_ARM64_REG_X0);assert 0<n<0x400000,n
            progress['allocations']+=1
            progress['allocation_bytes'].append(n)
            if progress['lose_claim'] and progress['allocations']==2:
                m.put(slot,old_descriptor)
            if progress['foreign_fonts'] and progress['allocations']==3:
                m.put(fonts_slot,fonts+0x1000000)
            if progress['foreign_attributes'] and progress['allocations']==3:
                m.put(attributes_slot,attributes+0x1000000)
            result=0 if progress['allocations']==progress['fail_at'] else progress['next']
            if result:
                progress['next']+=(n+15)&~15
                assert progress['next']<arena+0x2000000
        elif pc==0x40d32f98 and progress['mutex_failure']:result=0
        cpu.reg_write(arm.UC_ARM64_REG_X0,result)
        cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))

    def publication(cpu,access,address,size,value,data):
        if address!=slot:return
        if value==old_descriptor:kind='stock'
        else:
            kind='ready' if m.get(value+64,'I')==0x465a634d else 'preparing'
            if kind=='preparing':
                assert bytes(u.mem_read(value,64))==bytes(u.mem_read(old_descriptor,64))
                assert m.get(value+64)==0
            else:
                assert m.get(value+68,'I')==1
                assert m.get(value+32,'H')==51
                assert m.get(fonts_slot)!=fonts and m.get(attributes_slot)!=attributes
        progress['publication'].append(kind)

    watched={symbols[n] for n in receipt['hooks'].values()}
    watched|={symbols['fx_z63_system_after_start'],symbols['fx_z63_menu_install']}
    for pc in (*substitutes,*watched,guard+0x28):u.hook_add(UC_HOOK_CODE,observe,begin=pc,end=pc)
    u.hook_add(UC_HOOK_MEM_WRITE,publication,begin=slot,end=slot+7)

    def trial(fail_at=0,mutex_failure=False,blank_core=False,lose_claim=False,bad_setup=False,
              foreign_fonts=False,foreign_attributes=False):
        progress.clear();progress.update(stock_returned=False,consumers=[],core_entries=0,
            allocations=0,allocation_bytes=[],fail_at=fail_at,mutex_failure=mutex_failure,lose_claim=lose_claim,
            foreign_fonts=foreign_fonts,foreign_attributes=foreign_attributes,next=arena+0x20000,publication=[])
        # Each trial gets original setup/font roots and fresh supplied heap.
        m.put(slot,old_descriptor);m.put(fonts_slot,fonts);m.put(attributes_slot,attributes)
        m.put(old_descriptor+32,49 if bad_setup else 50,'H')
        progress['publication'].clear()
        u.mem_write(arena,b'\x01'*3285)
        u.mem_write(fonts+0x1000000,b'\x01'*3285)
        for language in range(29):
            row=arena+0x2000+language*0x1000
            u.mem_write(row,b'\x02'*3285);m.put(attributes+language*8,row)
            m.put(attributes+0x1000000+language*8,row)
        u.mem_write(arena+0x20000,bytes(0x200000))
        u.mem_write(message,bytes(64));m.put(message+32,20,'I')
        if blank_core:
            u.mem_write(core_begin,bytes(core_end-core_begin-8));u.ctl_remove_cache(core_begin,core_end)
        else:
            u.mem_write(core_begin,image[core_begin-0x40160000:core_end-0x40160000]);u.ctl_remove_cache(core_begin,core_end)
        u.reg_write(arm.UC_ARM64_REG_SP,0x1fe000);u.reg_write(arm.UC_ARM64_REG_LR,0x1ffff0)
        u.reg_write(arm.UC_ARM64_REG_X0,message);u.reg_write(arm.UC_ARM64_REG_X1,0)
        u.emu_start(0x40d66ef0,0x1ffff0,count=10000000)
        assert u.reg_read(arm.UC_ARM64_REG_PC)==0x1ffff0,hex(u.reg_read(arm.UC_ARM64_REG_PC))
        value=u.reg_read(arm.UC_ARM64_REG_X0)
        assert value==1 and progress['stock_returned']
        if receipt.get('activation'):assert m.get(0xa1722cfe0,'I')==0,'initializer stranded the clean update route'
        published=m.get(slot)!=old_descriptor
        if not published:
            assert m.get(fonts_slot)==fonts+(0x1000000 if foreign_fonts else 0)
            assert m.get(attributes_slot)==attributes+(0x1000000 if foreign_attributes else 0)
        return dict(fail_at=fail_at,mutex_failure=mutex_failure,blank_core=blank_core,lose_claim=lose_claim,bad_setup=bad_setup,
                    foreign_fonts=foreign_fonts,foreign_attributes=foreign_attributes,
                    allocations=progress['allocations'],allocation_bytes=progress['allocation_bytes'],published=published,
                    publication=list(progress['publication']),core_entries=progress['core_entries'],
                    stock_consumers_completed=True,stock_result_preserved=True)

    success=trial();assert success['published'],success
    failures=[]
    for index in range(1,success['allocations']+1):
        result=trial(index);assert not result['published'],result;failures.append(result)
    result=trial(mutex_failure=True);assert not result['published'];failures.append(result)
    result=trial(blank_core=True);assert not result['published'] and result['core_entries']==0 and result['allocations']==0;failures.append(result)
    result=trial(lose_claim=True);assert not result['published'];failures.append(result)
    result=trial(bad_setup=True);assert not result['published'] and result['allocations']==0;failures.append(result)
    for options in ({'foreign_fonts':True},{'foreign_attributes':True},
                    {'lose_claim':True,'foreign_fonts':True,'foreign_attributes':True}):
        result=trial(**options);assert not result['published'];failures.append(result)
    if receipt.get('activation'):
        trial();m.put(0xa1722cfe0,2,'I')
        def guarded_call(pc,*arguments):
            u.reg_write(arm.UC_ARM64_REG_SP,0x1fe000);u.reg_write(arm.UC_ARM64_REG_LR,0x1ffff0)
            for i in range(8):u.reg_write(arm.UC_ARM64_REG_X0+i,arguments[i] if i<len(arguments) else 0)
            u.emu_start(pc,0x1ffff0,count=10000000)
            assert u.reg_read(arm.UC_ARM64_REG_PC)==0x1ffff0
            return u.reg_read(arm.UC_ARM64_REG_X0)
        page=guarded_call(0x403edb18,2,0x7000)
        assert page and m.get(page,'I')>>16==0x7000,'updater admission abandoned the published shell'
        guarded_call(0x40339f30,0,3285,0x180100,0x180108)
        assert m.get(0x180108,'I')==16
        assert bytes(u.mem_read(m.get(0x180100),16))=='Fenestra'.encode('utf-16le')
        # Run the real startup worker after updater admission. It must retire
        # without opening files, then reject another command even if the
        # fixture resets the arbitration word for the next independent test.
        from host.elf_symbols import local_function
        worker,_=local_function(build/'probe.elf','startup.c','worker')
        boot_meta=struct.unpack_from('<7I',image,symbols['fx_z63_startup_layout']-0x40160000)
        startup=m.get(slot)+boot_meta[2]
        m.run(worker,startup)
        assert m.get(startup+boot_meta[3],'I')==7 and m.get(startup+boot_meta[5],'I')==2
        assert m.get(startup+boot_meta[6],'I')==1
        m.put(0xa1722cfe0,0,'I')
        assert m.run(symbols['fx_z63_startup_request'],startup,1)==2
    busy_cases=0
    if receipt.get('video') and receipt.get('activation'):
        trial();owner=m.get(slot)
        activation_meta=struct.unpack_from('<7I',image,symbols['fx_z63_activation_layout']-0x40160000)
        video_meta=struct.unpack_from('<9I',image,symbols['fx_z63_video_layout']-0x40160000)
        join_meta=struct.unpack_from('<10I',image,symbols['fx_z63_late_join_layout']-0x40160000)
        video=owner+video_meta[2];gate=owner+activation_meta[3]
        m.put(gate,3,'I') # Draining keeps the wrappers for outstanding native work.
        for policy in join_meta[4:7]:
            for member in (join_meta[8],join_meta[8]+4,0,4,20,32):
                address=video+policy+member;m.put(address,1,'I')
                assert m.run(symbols['activation_quiesced'],owner)==5
                assert m.get(gate,'I')==3,'busy retirement closed the feature gate'
                m.put(address,0,'I');busy_cases+=1
        assert m.run(symbols['activation_quiesced'],owner)==0
        assert m.get(gate,'I')==0
    trial()
    startup_layout=struct.unpack_from('<7I',image,symbols['fx_z63_startup_layout']-0x40160000)
    assert startup_layout[:2]==(0x46584236,1)
    startup=m.get(slot)+startup_layout[2]
    allow_start=[False];task_attempts=[]
    def task_probe(cpu,pc,size,data):
        assert allow_start[0],'late task start after permanent shutdown'
        task_attempts.append(True)
        cpu.reg_write(arm.UC_ARM64_REG_X0,4) # Supplied budget refusal; no task runs.
        cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))
    u.hook_add(UC_HOOK_CODE,task_probe,begin=symbols['fx_z63_task_start'],end=symbols['fx_z63_task_start'])
    def forbidden_task(cpu,pc,size,data):
        raise AssertionError('late task creation after permanent shutdown')
    u.hook_add(UC_HOOK_CODE,forbidden_task,begin=0x4018afb8,end=0x4018afb8)
    m.run(symbols['fx_z63_menu_lifecycle'],8)
    assert m.get(startup+startup_layout[6],'I')==1
    m.run(symbols['fx_z63_menu_lifecycle'],25)
    assert m.run(symbols['fx_z63_startup_start'],startup)==2
    # A controller allocated before closure but published afterwards must
    # inherit STOP before its task can begin filesystem discovery.
    delayed_runtime=arena+0x1800000
    u.mem_write(delayed_runtime,bytes(0x10000))
    runtime_meta=struct.unpack_from('<5I',image,symbols['fx_z63_runtime_layout']-0x40160000)
    count_offset=runtime_meta[4]
    m.run(symbols['fx_z63_menu_set_runtime'],delayed_runtime)
    assert m.get(delayed_runtime+count_offset+4,'I')==1,'late runtime missed shutdown'
    trial();allow_start[0]=True
    m.run(symbols['fx_z63_menu_lifecycle'],24)
    m.run(symbols['fx_z63_menu_lifecycle'],25)
    assert len(task_attempts)==1
    report={'passed':True,'candidate_sha256':receipt['candidate_sha256'],'success':success,
            'failures':failures,'shutdown_before_first_start_blocks_late_mount':True,
            'card_removal_before_first_start_keeps_mount_admission':True,
            'runtime_published_after_shutdown_inherits_stop':True,
            'clean_update_route_released_after_all_initializer_returns':True,
            'published_shell_lookup_and_text_survive_updater_admission':True,
            'updater_session_retires_startup_worker_and_blocks_new_commands':True,
            'busy_native_fields_refuse_hook_retirement':busy_cases,
            'task_start_fixture':'One supplied budget refusal checks mount admission; no task executes.',
            'scope':__doc__,'physical_camera_tested':False,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'substituted_calls':[hex(x) for x in substitutes]}
    Path(output).write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('main','build','output'):p.add_argument('--'+name,required=True)
    print(json.dumps(verify(**vars(p.parse_args())),indent=2))
