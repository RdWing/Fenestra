"""Execute linked RAW hooks with synthetic native idle, mutex and property inputs.

This checks the candidate's instructions and admission states, not firmware boot.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM64,UC_MODE_ARM,UC_HOOK_CODE
from unicorn.arm64_const import *


def check(directory):
    directory=Path(directory);receipt=json.loads((directory/'probe.json').read_text());symbols=receipt['symbols']
    image=(directory/'probe.eg.bin').read_bytes();base=0x40160000
    candidate_sha256=hashlib.sha256(image).hexdigest()
    if receipt.get('target')!='z63-c201' or candidate_sha256!=receipt.get('candidate_sha256'):
        raise ValueError('Candidate identity differs from the build receipt')
    reference_path=Path(__file__).with_name('log3g10_reference.json')
    reference=json.loads(reference_path.read_text());expected=bytes.fromhex(reference['matrix_hex'])
    if (reference['source_commit']!='6ee37b7bb95074592c8989a96eaafc7ab4c23a51' or
            reference['source_path']!='crates/core/src/r3d.rs' or len(expected)!=37):
        raise ValueError('Matrix source identity differs')
    u=Uc(UC_ARCH_ARM64,UC_MODE_ARM);u.mem_map(base,(len(image)+4095)&~4095);u.mem_write(base,image)
    u.mem_map(0x10000000,0x40000);u.reg_write(UC_ARM64_REG_CPACR_EL1,3<<20)
    file_type=[6];mutex_ok=[1]
    cases={'matrix_callbacks':0,'template_copies':0,'extension_cases':0,
           'wrong_mode_refusals':0,'mode_property_changes':0}
    state=0x10000000;owner=0x10001000;cookie=0x10002000;q=0x10003000;reply=0x10004000;out=0x10010000;stop=0x1003e000
    for address in [0xa048bb044,0xa03324ce0,0xa03324dc8,0xa03d42100]:
        try:u.mem_map(address&~4095,4096)
        except Exception:pass
    def put(address,fmt,*values):u.mem_write(address,struct.pack(fmt,*values))
    def get(address,fmt):return struct.unpack(fmt,u.mem_read(address,struct.calcsize(fmt)))[0]
    def ret(value):u.reg_write(UC_ARM64_REG_X0,value);u.reg_write(UC_ARM64_REG_PC,u.reg_read(UC_ARM64_REG_LR))
    def stub(uc,pc,size,user):
        if pc==symbols['fx_z63_menu_video']:ret(state)
        elif pc==0x40d32f74:ret(mutex_ok[0])
        elif pc==0x40d32f60:ret(1)
        elif pc==0x403ffcd0:ret(file_type[0])
        elif pc==0x40ce5b70:
            dst=u.reg_read(UC_ARM64_REG_X0);src=u.reg_read(UC_ARM64_REG_X1);n=u.reg_read(UC_ARM64_REG_X2)
            assert n<=65536;u.mem_write(dst,bytes(u.mem_read(src,n)));ret(1)
    for address in [symbols['fx_z63_menu_video'],0x40d32f74,0x40d32f60,0x403ffcd0,0x40ce5b70]:u.hook_add(UC_HOOK_CODE,stub,begin=address,end=address)
    def call(address,*args):
        u.reg_write(UC_ARM64_REG_SP,0x1003f000);u.reg_write(UC_ARM64_REG_LR,stop)
        for i in range(8):u.reg_write(UC_ARM64_REG_X0+i,args[i] if i<len(args) else 0)
        u.emu_start(address,stop,count=100000)
        assert u.reg_read(UC_ARM64_REG_PC)==stop,'instruction budget exhausted'
        return u.reg_read(UC_ARM64_REG_X0)
    def resource(op):return call(symbols['fx_z63_raw_resource'],0,op,0,owner,7,cookie,q,reply)
    def request(op,choice=None):
        u.mem_write(q,bytes(816));put(q+32,'<Q',op)
        if choice is not None:put(q+12,'<I',16);put(q+48,'<IIII',1,16,3,choice)
        return resource(3)
    def matrix(value,context=0):
        u.mem_write(out,b'\xa5'*80)
        assert call(0x4109f858,context,out+16)==37
        assert bytes(u.mem_read(out,80))==b'\xa5'*16+value+b'\xa5'*27
        cases['matrix_callbacks']+=1
    def template(source,length,active):
        value=image[source-base:source-base+length]
        assert len(value)==length
        if active and source in (0x42b7153a,0x42b71590) and length==86:
            value=value[:4]+b'NR3D'+value[8:]
        u.mem_write(out,b'\xa5'*128)
        call(symbols['fx_z63_raw_template_copy'],out+16,source,length)
        assert bytes(u.mem_read(out,128))==b'\xa5'*16+value+b'\xa5'*(112-length)
        cases['template_copies']+=1
    def templates(active):
        for source,length in ((0x42b7153a,86),(0x42b71590,86),(0x42b714ca,86),
                              (0x42b7153a,85),(0x42b71590,87),(0x42b7153b,86)):
            template(source,length,active)
    extension_names=('JPG','HIF','NEF','TIF','NDF','MOV','NEV','MP4','WAV','~OV','~EV','~P4','TMP')
    def extensions(active,indices=range(15)):
        for index in indices:
            ptr=call(0x408bc518,index if index!=14 else 0xffffffff)
            if index>=13:assert ptr==0
            else:
                name='R3D' if active and index==6 else extension_names[index]
                assert bytes(u.mem_read(ptr,4))==name.encode()+b'\0'
            cases['extension_cases']+=1
    stock=bytes.fromhex('003f1b090e3ec335e2bd152ea63e69b76a3f862ffebe8d9bac3bcd1418be3139d23fa0c065')
    assert resource(1)==2 and get(cookie,'<Q')==0
    put(state+8,'<I',3);put(state+48,'<I',3);put(state+96,'<I',1)
    assert resource(1)==0 and get(cookie,'<Q')==7
    result=request(0);assert result==0 and get(reply+60,'<I')==3
    assert call(symbols['fx_z63_raw_resource'],0,3,0,owner,8,cookie,q,reply)==6
    for kind in (0,1,2,3,4,5,7,0xffffffff):
        file_type[0]=kind
        before=bytes(u.mem_read(state,80))
        assert request(2,1)==2 and bytes(u.mem_read(state,80))==before
        cases['wrong_mode_refusals']+=1
    file_type[0]=6;assert request(2,2)==1 and get(state+44,'<I')==0
    # The patched original entry executes Stock before selection.
    matrix(stock);templates(False);extensions(False)
    mutex_ok[0]=0;before=bytes(u.mem_read(state,80))
    assert request(2,1)==5 and bytes(u.mem_read(state,80))==before
    mutex_ok[0]=1
    put(0xa03d42100,'<I',1) # Busy: accept requested state but do not publish it.
    assert request(2,1)==0 and get(state+44,'<I')==1 and get(state+40,'<I')==0
    put(0xa03d42100,'<I',2)
    assert request(1)==0 and get(state+40,'<I')==1
    templates(True);extensions(True)
    for src in (0x42b7153a,0x42b71590):
        template(src,86,True)
        for frame in range(8):matrix(expected,0x10020000+frame*0x100)
    # A changed property does not retire the selected profile. The original
    # extension switch still confines replacement to its NEV case.
    for kind in (3,4,5):
        file_type[0]=kind
        assert request(1)==0 and get(state+40,'<I')==1
        extensions(True,(5,6,7));cases['mode_property_changes']+=1
    file_type[0]=6
    put(0xa03d42100,'<I',1);assert resource(2)==5 and get(cookie,'<Q')==7
    put(0xa03d42100,'<I',2);assert resource(2)==0 and get(cookie,'<Q')==0 and get(state+40,'<I')==0
    matrix(stock);templates(False);extensions(False)
    assert resource(1)==0;put(state+4,'<I',1)
    assert request(2,1)==5 and get(state+44,'<I')==0
    put(state+4,'<I',0);assert request(2,1)==0 and get(state+40,'<I')==1
    # Active native work defers Stock even when the supplied idle words agree.
    put(state+52,'<I',1)
    assert request(2,0)==0 and get(state+44,'<I')==0 and get(state+40,'<I')==1
    assert request(1)==0 and get(reply+80,'<I')==1
    put(state+52,'<I',0)
    assert request(1)==0 and get(state+40,'<I')==0
    # A tracking fault retains the profile and owner through failed retirement.
    assert request(2,1)==0 and get(state+40,'<I')==1
    retained_owner=get(state+72,'<Q');transitions=get(state+64,'<I')
    put(state+68,'<I',1)
    assert request(2,0)==2 and get(state+44,'<I')==1 and get(state+40,'<I')==1
    assert get(state+72,'<Q')==retained_owner and get(state+64,'<I')==transitions
    assert request(1)==0 and get(reply+84,'<I')==1 and get(reply+64,'<I')==1
    assert resource(2)==5 and get(cookie,'<Q')==7
    assert get(state+60,'<I')==1 and get(state+44,'<I')==0 and get(state+40,'<I')==1
    assert resource(4)==5 and get(cookie,'<Q')==7 and get(state+72,'<Q')==retained_owner
    matrix(expected);extensions(True,(5,6,7))
    print(json.dumps({'raw_hook_execution':True,'stock_and_restore':True,'pending_idle_and_drain':True,
        'prores_conflict':True,'mutex_refusal_unchanged':True,'fault_retains_effective_and_owner':True,
        'cases':cases,'candidate_sha256':candidate_sha256,
        'matrix_source_commit':reference['source_commit'],'matrix_source_path':reference['source_path'],
        'matrix_sha256':hashlib.sha256(expected).hexdigest(),
        'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'synthetic_native_inputs':True,'managed_capability_routing_tested':False,
        'mode_transition_freshness_qualified':False,'firmware_boot':False,'physical_camera':False},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('candidate');check(p.parse_args().candidate)
