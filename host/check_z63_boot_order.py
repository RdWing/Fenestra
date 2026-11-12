"""Full-system stock-first startup controls on disposable virtual storage.

Uses a host-supplied flash image, not the physical reset/load path. The
--no-image-preload control requires MAIN to copy its own DRAM code windows.
initializer-return fixture is deliberately modified test code, not a release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from build_z63_adapter import load_application
from z63_core_absent_smoke import boot
from z63_emulator_smoke import scanout_fraction
from z63_placement import guards, MARKER
from z63_activation import profile_for


def live_colour(path):
    magic,dimensions,depth,data=Path(path).read_bytes().split(b'\n',3)
    width,height=map(int,dimensions.split())
    if magic!=b'P6' or depth!=b'255' or len(data)!=width*height*3:raise ValueError('unexpected scanout')
    count=0
    for i in range(0,len(data),3):
        pixel=data[i:i+3]
        count+=max(pixel)>=80 and max(pixel)-min(pixel)>=40
    return count/(width*height)


def main():
    sources={name:(Path(__file__).parent/name).read_bytes() for name in (
        'check_z63_boot_order.py','z63_core_absent_smoke.py','z63_emulator_smoke.py',
        'z63_placement.py','z63_activation.py','build_z63_adapter.py')}
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('qemu','original','application','receipt','loader','snor','nand','mcu','card','raw','plugin','output-dir'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--seconds',type=float,default=35)
    p.add_argument('--no-image-preload',action='store_true')
    p.add_argument('--card-absent',action='store_true',help='hold modeled card detection absent from startup')
    p.add_argument('--stale-state',action='store_true',help='supply a stale owned-looking descriptor before MAIN resets its data')
    p.add_argument('--controls',nargs='+',choices=('stock','intact','absent-core-marker-kept','initializer-no-state'),
                   default=('stock','intact','absent-core-marker-kept','initializer-no-state'))
    p.add_argument('--require-live-colour',action='store_true',help='require the supplied synthetic colour-bar fixture to reach visible preview')
    a=p.parse_args();profile,original=load_application(a.original)
    if a.controls[0]!='stock' or len(set(a.controls))!=len(a.controls):raise ValueError('unique controls must start with stock')
    image=a.application.read_bytes();r=json.loads(a.receipt.read_text())
    if hashlib.sha256(image).hexdigest()!=r['candidate_sha256']:raise ValueError('candidate differs')
    if not r.get('menu') or not profile.get('late_initialization'):raise ValueError('late menu core required')
    out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'harness-source').mkdir()
    for name,content in sources.items():(out/'harness-source'/name).write_bytes(content)
    base=profile['image_base'];begin,end=r['placement']['code_region']
    entry=r['symbols']['fx_z63_system_after_start'];dispatch=profile['sysctl']['dispatcher']
    stock_return=int(r['guards'][hex(dispatch)],16)+0x28
    ordinary={r['symbols'][name] for name in r['hooks'].values()}
    copy_entries={row['address'] for row in profile['text_relocation']['routines']}
    watch=sorted(ordinary|{entry,stock_return,r['symbols']['fx_z63_menu_install']}|copy_entries)
    absent=bytearray(image);absent[begin-base:end-base-8]=bytes(end-begin-8)
    assert absent[end-base-8:end-base]==MARKER
    inactive=bytearray(image);struct.pack_into('<I',inactive,entry-base,0xd65f03c0)
    calls={row['address'] for row in profile['ui_calls']}
    if r.get('video'):calls.update(row['address'] for row in profile['video_quality']['hooks'] if row.get('link'))
    hooks={int(site,16):(r['symbols'][name],int(site,16) in calls) for site,name in r['hooks'].items()}
    guard_bytes,table=guards(profile_for(profile,r.get('runtime')),original,hooks,inactive[begin-base:end-base],entry,bytes.fromhex(r['build_identity']))
    assert table=={int(k,16):int(v,16) for k,v in r['guards'].items()}
    offset=profile['guard_region']['begin']-base;inactive[offset:offset+len(guard_bytes)]=guard_bytes
    images={'stock':original,'intact':image,'absent-core-marker-kept':absent,'initializer-no-state':inactive}
    results={}
    for name in a.controls:
        data=images[name]
        path=out/(name+'.DO_NOT_FLASH.eg.bin');path.write_bytes(data)
        # W3's destination is the original C2.01 copy binding. Read only the
        # guard reservation, not arbitrary or per-camera memory.
        g0,g1=(profile['guard_region'][k] for k in ('begin','end'))
        status,lines=boot(a,path,out/name,watch,
                          [('copied-guards.bin',0xa17200000+g0-0x40168000,g1-g0),
                           ('setup-root.bin',profile['late_initialization']['descriptor_slot'],8)])
        pcs=[int(re.search(r'call pc=(0x[0-9a-f]+)',line).group(1),16) for line in lines]
        completed=[i for i,pc in enumerate(pcs) if pc==stock_return]
        first=completed[0] if completed else len(pcs)
        record={'running':bool(status.get('running')),'image_sha256':hashlib.sha256(data).hexdigest(),
                'stock_completion_returns':len(completed),
                'core_entries_before_stock_return':sum(pc in ordinary or pc==entry or pc==r['symbols']['fx_z63_menu_install'] for pc in pcs[:first]),
                'initializer_entries':pcs.count(entry),'ordinary_core_entries':sum(pc in ordinary for pc in pcs)}
        if a.card_absent:record['card_detected']=status['card_detected']
        root=int.from_bytes((out/name/'setup-root.bin').read_bytes(),'little')
        record['final_setup_descriptor']=hex(root)
        if name!='intact':assert root==profile['late_initialization']['original_descriptor'],record
        if a.stale_state:
            record['stale_fixture_verified_before_main']=True
            record['stale_active_and_session_verified_before_main']=True
            assert root!=0xa10000000,record
        copied=(out/name/'copied-guards.bin').read_bytes()
        record['copied_guards_match']=copied==data[g0-base:g1-base]
        record['live_colour_fraction']=live_colour(out/name/'screen.ppm')
        if a.require_live_colour:assert record['live_colour_fraction']>.20,record
        record['copy_routine_entries']={hex(pc):pcs.count(pc) for pc in sorted(copy_entries)}
        assert record['copied_guards_match'],record
        if a.no_image_preload:assert all(record['copy_routine_entries'].values()),record
        if name!='stock':
            record['scanout_match']=scanout_fraction(out/'stock/screen.ppm',out/name/'screen.ppm')
            assert completed and not record['core_entries_before_stock_return'],record
            if name!='intact':
                assert not record['ordinary_core_entries'] and record['scanout_match']>=.90,record
            assert record['initializer_entries']==(0 if name=='absent-core-marker-kept' else len(completed)),record
        assert record['running'],record
        results[name]=record
        (out/'progress.json').write_text(json.dumps(results,indent=2)+'\n')
    result={'passed':True,'candidate_sha256':r['candidate_sha256'],'seconds_per_boot':a.seconds,
            'controls':results,'emulator_only':True,'physical_camera_tested':False,
            'dram_windows_preloaded':not a.no_image_preload,
            'card_detection_held_absent':a.card_absent,
            'stale_descriptor_fixture':a.stale_state,
            'live_colour_required':a.require_live_colour,
            'source_sha256':hashlib.sha256(sources['check_z63_boot_order.py']).hexdigest(),
            'source_inputs':{name:hashlib.sha256(content).hexdigest() for name,content in sources.items()},
            'qemu_sha256':hashlib.sha256(a.qemu.read_bytes()).hexdigest(),
            'loader_sha256':hashlib.sha256(a.loader.read_bytes()).hexdigest(),
            'plugin_sha256':hashlib.sha256(a.plugin.read_bytes()).hexdigest(),
            'scope':__doc__}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
