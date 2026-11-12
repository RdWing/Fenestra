"""Original menu status mapping through both actual updater admission guards.

Two original API preparation helpers and deep update starts are substitutes.
No package scan, programmer, controller or physical camera executes here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'host'))
from host.check_zr_color_transplant import Original
from z63_activation import CONTROL_RAM
from unicorn import UC_HOOK_CODE
import unicorn.arm64_const as arm


def verify(main,build,output):
    b=Path(build);r=json.loads((b/'probe.json').read_text());image=(b/'probe.eg.bin').read_bytes()
    if hashlib.sha256(image).hexdigest()!=r['candidate_sha256']:raise ValueError('candidate differs')
    m=Original(main,'z63');u=m.u;u.mem_write(0x40160000,image[:-2]);u.mem_map(CONTROL_RAM&~4095,4096)
    calls=[];status=[2]
    def substituted(cpu,pc,size,data):
        calls.append(pc)
        cpu.reg_write(arm.UC_ARM64_REG_X0,status[0] if pc in (0x41014ed4,0x4101557c) else 0)
        cpu.reg_write(arm.UC_ARM64_REG_PC,cpu.reg_read(arm.UC_ARM64_REG_LR))
    for pc in (0x41014c74,0x4101760c,0x41014ed4,0x4101557c):
        u.hook_add(UC_HOOK_CODE,substituted,begin=pc,end=pc)
    rows=[];begin,end=r['placement']['code_region']
    for absent in (False,True):
        u.mem_write(begin,bytes(end-begin) if absent else image[begin-0x40160000:end-0x40160000]);u.ctl_remove_cache(begin,end)
        for menu,start in ((0x40401800,0x41014ed4),(0x4040193c,0x4101557c)):
            for latch in (0,1,2,3,0xffffffff):
                m.put(CONTROL_RAM,latch,'I');calls.clear();status[0]=2
                result=m.run(menu,0,0)
                expected=[0x41014c74,0x4101760c]+([start] if latch in (0,2) else [])
                assert calls==expected,(hex(menu),latch,[hex(pc) for pc in calls])
                assert result==1 and m.get(CONTROL_RAM,'I')==(2 if latch in (0,2) else latch)
                rows.append(dict(menu=hex(menu),latch=latch,core_absent=absent,
                    updater_entered=start in calls,menu_result=result,session_after=m.get(CONTROL_RAM,'I')))
    mappings=[]
    for menu in (0x40401800,0x4040193c):
        for supplied,expected in ((0,0),(1,8),(2,1)):
            m.put(CONTROL_RAM,0,'I');status[0]=supplied
            result=m.run(menu,0,0);assert result==expected
            mappings.append(dict(menu=hex(menu),updater_result=supplied,menu_result=result))
    result=dict(passed=True,candidate_sha256=r['candidate_sha256'],cases=rows,original_status_mapping=mappings,
        scope=__doc__,substituted_calls=['0x41014C74','0x4101760C','0x41014ED4','0x4101557C'],
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),physical_camera_tested=False)
    p=Path(output)
    if p.exists():raise ValueError('new output required')
    p.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('main','build','output'):p.add_argument('--'+key,required=True)
    print(json.dumps(verify(**vars(p.parse_args())),indent=2))
