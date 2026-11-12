"""Execute actual interior hooks against pristine Stock instructions locally.

Original firmware and linked build remain external. Hostile AAPCS helper
substitutions isolate the assembly preservation contract, not the C backend.
"""
import argparse
import json
from pathlib import Path
import struct
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
import unicorn.arm64_const as arm


def verify_guards(original, candidate, receipt):
    """Compare each installed guard's two routes with the source instruction."""
    if not receipt.get('guards'):
        return 0
    base = 0x40160000
    cpu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu.mem_map(base, (len(candidate) + 4095) & ~4095)
    cpu.mem_write(base, candidate)
    cpu.mem_map(0x800000, 0x20000)
    profile=json.loads((Path(__file__).resolve().parents[1]/'targets/z63-c201.json').read_text())
    late=profile.get('late_initialization') if receipt.get('menu') else None
    if late:
        cpu.mem_map(late['descriptor_slot']&~4095,4096)
        cpu.mem_map(0xa01000000,4096)
        cpu.mem_write(late['descriptor_slot'],struct.pack('<Q',0xa01000000))
        cpu.mem_write(0xa01000000+64,struct.pack('<I',late['state_magic']))
        cpu.mem_write(0xa01000000+76,struct.pack('<I',1))
    if receipt.get('activation'):cpu.mem_map(0xa17200000,0x30000)
    marker = receipt['placement']['code_region'][1] - 8
    marker_bytes = candidate[marker-base:marker-base+8]
    regs = [getattr(arm, 'UC_ARM64_REG_X'+str(i)) for i in range(31)]
    state_regs = [*regs, arm.UC_ARM64_REG_SP, arm.UC_ARM64_REG_NZCV]
    initial = [0x10203040 + i*0x101 for i in range(31)] + [0x810000, 0xa0000000]
    initial[0] = 0x800100
    initial[8] = 0x800000

    def execute(site, stop):
        for register, value in zip(state_regs, initial):
            cpu.reg_write(register, value)
        cpu.emu_start(site, stop, count=(marker-base+8)*8+1000)
        if cpu.reg_read(arm.UC_ARM64_REG_PC) != stop:
            raise ValueError('video guard did not reach the expected destination')
        return [cpu.reg_read(register) for register in state_regs]

    checks = 0
    for address, symbol in receipt['hooks'].items():
        if not symbol.startswith(('fx_z63_video_', 'fx_z63_raw_', 'fx_z63_h265_')):
            continue
        site = int(address, 16)
        stock = original[site-base:site-base+4]
        patched = candidate[site-base:site-base+4]
        word, = struct.unpack('<I', stock)
        is_call = word >> 26 == 0x25
        if receipt.get('activation'):
            from z63_placement import _branch
            if patched!=stock:raise ValueError('feature hook was flashed before activation')
            patched=struct.pack('<I',_branch(site,int(receipt['guards'][address],16),is_call))
        delta = word & 0x3ffffff
        if delta & (1 << 25):
            delta -= 1 << 26
        continuation = site + delta*4 if word >> 26 in (5, 0x25) else site+4
        cpu.mem_write(site, stock)
        cpu.ctl_remove_cache(site, site+4)
        expected = execute(site, continuation)
        cpu.mem_write(site, patched)
        cpu.ctl_remove_cache(site, site+4)
        cpu.mem_write(marker, bytes(8))
        if execute(site, continuation) != expected:
            raise ValueError('video guard Stock fallback changes registers or flags: '+address)
        cpu.mem_write(marker, marker_bytes)
        present = initial.copy()
        if is_call:
            present[30] = site+4
        if execute(site, receipt['symbols'][symbol]) != present:
            raise ValueError('video guard changes incoming registers or flags: '+address)
        checks += 2
    return checks


def verify(original,build):
    original=Path(original).read_bytes();build=Path(build)
    receipt=json.loads((build/'probe.json').read_text());symbols=receipt['symbols']
    code=(build/'probe.bin').read_bytes();base=0x40160000;code_base=symbols.get('fx_z63_core_begin',0x40910000)
    guard_checks = verify_guards(original, (build/'probe.eg.bin').read_bytes(), receipt) if receipt.get('guards') else 0
    regs=[getattr(arm,'UC_ARM64_REG_X'+str(i)) for i in range(31)]
    vectors=[getattr(arm,'UC_ARM64_REG_Q'+str(i)) for i in range(32)]
    cases=[]
    def execute(start,ends,stock,choice,word):
        u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        u.mem_map(code_base,(len(code)+4095)&~4095);u.mem_write(code_base,code)
        pages={a&~4095 for a in [start,*ends] if not code_base<=a<code_base+len(code)}
        for page in pages:
            u.mem_map(page,4096);u.mem_write(page,original[page-base:page-base+4096])
        u.mem_map(0x42beb000,4096);u.mem_write(0x42beb000,original[0x42beb000-base:0x42beb000-base+4096])
        u.mem_map(0x800000,0x20000);u.mem_map(0x900000,0x2000)
        for i,r in enumerate(regs):u.reg_write(r,0x1122334400000000+i*0x101)
        for i,r in enumerate(vectors):u.reg_write(r,0x102030405060708090a0b0c0d0e00000+i)
        u.reg_write(arm.UC_ARM64_REG_SP,0x810000)
        u.reg_write(arm.UC_ARM64_REG_CPACR_EL1,3<<20)
        u.reg_write(arm.UC_ARM64_REG_NZCV,0xa0000000)
        u.reg_write(arm.UC_ARM64_REG_FPCR,0x400000)
        u.reg_write(arm.UC_ARM64_REG_FPSR,0x08000010)
        u.reg_write(regs[0],word);u.reg_write(regs[8],0x900000);u.reg_write(regs[10],0x901000)
        u.mem_write(0x900000,struct.pack('<I',word))
        helpers={symbols[n]:n for n in ['fx_z63_video_code','fx_z63_video_template','fx_z63_video_shoot','fx_z63_video_parse','fx_z63_video_play']}
        stopped=[]
        def hook(mu,pc,size,context):
            if pc in ends:stopped.append(pc);mu.emu_stop();return
            if stock or pc not in helpers:return
            name=helpers[pc];lr=mu.reg_read(regs[30]);arg=mu.reg_read(regs[0])
            for i in range(19):mu.reg_write(regs[i],0x8877665500000000+i)
            for r in vectors:mu.reg_write(r,0)
            mu.reg_write(arm.UC_ARM64_REG_NZCV,0x50000000)
            mu.reg_write(arm.UC_ARM64_REG_FPCR,0);mu.reg_write(arm.UC_ARM64_REG_FPSR,0)
            if name.endswith('_play'):
                label=[b'ProRes 422 HQ',b'ProRes 422',b'ProRes 422 LT',b'ProRes Proxy'][max(0,choice-1)]
                mu.mem_write(arg,label.ljust(14,b'\0'))
            value=choice if name.endswith('_code') else 0x42b7145a if name.endswith('_template') else 0x4408a060 if name.endswith('_shoot') else int(arg in [0x61706368,0x6170636e,0x61706373,0x6170636f])
            mu.reg_write(regs[0],value);mu.reg_write(arm.UC_ARM64_REG_PC,lr)
        u.hook_add(UC_HOOK_CODE,hook)
        u.emu_start(start,0,count=10000)
        if not stopped:raise ValueError('video assembly did not reach continuation')
        return dict(pc=stopped[0],x=[u.reg_read(r) for r in regs],q=[u.reg_read(r) for r in vectors],
            sp=u.reg_read(arm.UC_ARM64_REG_SP),nzcv=u.reg_read(arm.UC_ARM64_REG_NZCV),
            fpcr=u.reg_read(arm.UC_ARM64_REG_FPCR),fpsr=u.reg_read(arm.UC_ARM64_REG_FPSR),
            written=bytes(u.mem_read(0x901000,4)).hex(),stack=bytes(u.mem_read(0x810000+128,192)).hex())
    for name,address,span in [('type',0x40d22a24,12),('template',0x40cefd20,20),('shoot',0x40519a20,28)]:
        for word in ([0,1,2,3,0xffffffff] if name=='type' else [0]):
            expected=execute(address,[address+span],True,0,word)
            actual=execute(symbols['fx_z63_video_'+name+'_hook'],[address+span],False,0,word)
            if expected!=actual:
                raise ValueError('Stock '+name+' differs: '+repr({k:(expected[k],actual[k]) for k in expected if expected[k]!=actual[k]}))
            cases.append(dict(hook=name,stock_word=word,stock_equivalent=True))
    for word in [0x61706368,0x6170636e,0x61706373,0x6170636f,0,0xffffffff]:
        ends=[0x40ceb340,0x40ceb420]
        expected=execute(0x40ceb330,ends,True,0,word)
        actual=execute(symbols['fx_z63_video_parser_hook'],ends,False,0,word)
        if expected!=actual:raise ValueError('Stock parser differs')
        cases.append(dict(hook='parser',fourcc=word,stock_equivalent=True))
    for choice in range(1,5):
        result=execute(symbols['fx_z63_video_type_hook'],[0x40d22a30],False,choice,0)
        if result['x'][8]!=choice-1 or result['nzcv']!=0x80000000:raise ValueError('enabled video quality admission differs')
        cases.append(dict(hook='type',choice=choice,admitted=True))
    expected=execute(0x4067c4d0,[0x4067c554],True,0,0)
    actual=execute(symbols['fx_z63_video_play_hook'],[0x4067c554],False,0,0)
    if actual!=expected:raise ValueError('Stock playback instruction effects or stack destination differ')
    cases.append(dict(hook='play',stock_equivalent=True))
    for choice in range(1,5):
        actual=execute(symbols['fx_z63_video_play_hook'],[0x4067c554],False,choice,0)
        stack=bytes.fromhex(actual['stack'])
        label=[b'ProRes 422 HQ',b'ProRes 422',b'ProRes 422 LT',b'ProRes Proxy'][choice-1].ljust(14,b'\0')
        if stack[:168]!=bytes(168) or stack[168:182]!=label or stack[182:]!=bytes(10):
            raise ValueError('Enabled playback changed bytes outside the native label')
        cases.append(dict(hook='play',choice=choice,stack_destination_matched=True))
    assembly_count=len(cases)
    # Execute the actual linked C consumers and original rate-index helper.
    # Only the menu-context getter is substituted with owned test RAM.
    def backend(choice):
        u=Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        u.mem_map(code_base,(len(code)+4095)&~4095);u.mem_write(code_base,code)
        for page,length in [(0x40d22000,4096),(0x42b71000,0x2000),(0x4408a000,4096)]:
            u.mem_map(page,length);u.mem_write(page,original[page-base:page-base+length])
        u.mem_map(0x800000,0x20000);u.mem_map(0x900000,0x4000)
        u.mem_write(0x900000,struct.pack('<I',choice))
        u.reg_write(arm.UC_ARM64_REG_CPACR_EL1,3<<20)
        def hook(mu,pc,size,context):
            if pc==0x903000:mu.emu_stop()
            elif pc==symbols['fx_z63_menu_video']:
                mu.reg_write(regs[0],0x900000);mu.reg_write(arm.UC_ARM64_REG_PC,mu.reg_read(regs[30]))
        u.hook_add(UC_HOOK_CODE,hook)
        def call(name,*args):
            u.reg_write(arm.UC_ARM64_REG_SP,0x810000);u.reg_write(regs[30],0x903000)
            for i,value in enumerate(args):u.reg_write(regs[i],value)
            u.emu_start(symbols['fx_z63_video_'+name],0,count=100000)
            if u.reg_read(arm.UC_ARM64_REG_PC)!=0x903000:raise ValueError('video C helper did not return')
            return u.reg_read(regs[0])
        return u,call
    indices=[(4,0),(4,5),(4,6),(5,2),(5,3),(5,4),(5,5),(5,6),(6,2),(6,3),(6,0),(6,1)]
    fourccs=[0x61706368,0x6170636e,0x61706373,0x6170636f]
    for choice in range(5):
        u,call=backend(choice)
        for index,(kind,rate) in enumerate(indices):
            u.mem_write(0x901000,struct.pack('<3I',0,kind,rate))
            call('rate',0x901000,0x901100)
            expected=bytearray(original[0x42b72828-base+index*24:0x42b72828-base+(index+1)*24])
            if choice>1:
                num,den=[(147,220),(102,220),(45,220)][choice-2]
                value=struct.unpack_from('<Q',expected,16)[0]
                struct.pack_into('<Q',expected,16,((value*num+den*(1<<19))//(den*(1<<20)))<<20)
            if bytes(u.mem_read(0x901100,24))!=expected:raise ValueError('linked rate/index data differs')
            cases.append(dict(helper='rate',choice=choice,index=index,matched=True))
        pointer=call('template');expected=bytearray(original[0x42b7145a-base:0x42b7145a-base+86])
        if choice:
            q=choice-1;label=[b'Apple ProRes 422 HQ',b'Apple ProRes 422',b'Apple ProRes 422 LT',b'Apple ProRes 422 Proxy'][q]
            expected[7]=b'hnso'[q];expected[50]=len(label);expected[51:82]=label.ljust(31,b'\0')
        if bytes(u.mem_read(pointer,86))!=expected:raise ValueError('linked sample description differs')
        cases.append(dict(helper='template',choice=choice,matched=True))
        for quality,fourcc in enumerate(fourccs):
            accepted=call('parse',fourcc)
            if accepted!=int(bool(choice) or quality==0):raise ValueError('linked playback recognition differs')
            if accepted:
                call('play',0x901100)
                label=bytes(u.mem_read(0x901100,14)).split(b'\0')[0]
                if label!=[b'ProRes 422 HQ',b'ProRes 422',b'ProRes 422 LT',b'ProRes Proxy'][quality]:raise ValueError('linked playback label differs')
            cases.append(dict(helper='playback',choice=choice,fourcc=fourcc,accepted=bool(accepted)))
        if call('parse',0):raise ValueError('linked parser accepts unknown fourcc')
        pointer=call('shoot');actual=list(struct.unpack('<14Q',u.mem_read(pointer,112)))
        expected=list(struct.unpack('<14Q',original[0x4408a060-base:0x4408a060-base+112]))
        if choice:
            at=next(i+1 for i in range(0,14,2) if expected[i]==4)
            label=bytes(u.mem_read(actual[at],16)).split(b'\0')[0]
            if label!=[b'ProRes 422 HQ',b'ProRes 422',b'ProRes 422 LT',b'ProRes Proxy'][choice-1]:raise ValueError('linked shooting label differs')
            actual[at]=expected[at]
        if actual!=expected:raise ValueError('linked shooting table changes other entries')
        cases.append(dict(helper='shoot',choice=choice,matched=True))
        if choice:
            call('parse',fourccs[3]);u.mem_write(0x900000,struct.pack('<I',0));call('play',0x901100)
            if bytes(u.mem_read(0x901100,14)).split(b'\0')[0]!=b'ProRes 422 HQ':
                raise ValueError('Stock playback retained an experimental clip label')
            cases.append(dict(helper='playback-stock-transition',previous_choice=choice,matched=True))
    return dict(guard_route_checks=guard_checks,passed=True,cases=len(cases),assembly_cases=assembly_count,backend_cases=len(cases)-assembly_count,results=cases,
        qualification='Actual linked assembly with hostile helper substitutes, plus linked C consumers/original index with a substituted context getter. No native scheduling, completed recording or physical acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--application',required=True);p.add_argument('--build',required=True)
    a=p.parse_args();print(json.dumps(verify(a.application,a.build),indent=2))
