"""Exact C2.01 RAM activation layout; no installer or nonvolatile writer."""
import binascii
import struct

CONTROL = 0x40194fe0
CONTROL_RAM = 0xa1722cfe0
UPDATE_SITES = ((0x410143ec, 0x41014ed4), (0x4101442c, 0x4101557c))
SHELL = frozenset((0x40d66ef0, 0x403edb18, 0x40339f30, 0x403c0464))


def profile_for(profile, runtime):
    result = dict(profile)
    if runtime:
        result['activation'] = dict(control=CONTROL, latch=CONTROL_RAM,
                                    permanent=sorted(SHELL))
    return result


def alias(site):
    for start, end, ram in ((0x40168000, 0x40195000, 0xa17200000),
                            (0x40200000, 0x4090ebe8, 0xa15c00000),
                            (0x40c00000, 0x416692f8, 0xa16600000)):
        if start <= site and site + 4 <= end and not site & 3:
            return ram + site - start
    raise ValueError('activation site is not in copied original text')


def enable_record(build_identity):
    if len(build_identity) != 32 or not any(build_identity):
        raise ValueError('exact nonzero build identity required')
    data = b'FX63ARM1' + build_identity + struct.pack('<I', 1) + bytes(16)
    return data + struct.pack('<I', binascii.crc32(data))


def ram_words(profile,original,hooks,calls):
    # Guard layout depends only on the hook set, not linked core addresses.
    # Generate before compilation so these records enter the immutable core
    # and its external CRC, without a circular build-identity dependency.
    from z63_placement import INTEGRITY_CODE,BOOTSTRAP_CODE,_branch
    at=profile['guard_region']['begin']+8+len(INTEGRITY_CODE)+80+1024+len(BOOTSTRAP_CODE)
    rows=[]
    for index,site in enumerate(sorted(hooks)):
        if site in SHELL:continue
        alias(site)
        rows.append((site,struct.unpack_from('<I',original,site-profile['image_base'])[0],
                     _branch(site,at+index*48,site in calls)))
    return rows


def header(rows):
    return ('__attribute__((used,retain)) const FxActivationWord fx_z63_activation_words[]={\n'+
            (''.join('    {0x%xu,0x%xu,0x%xu},\n'%row for row in rows) if rows else '    {0u,0u,0u},\n')+'};\n'+
            '__attribute__((used,retain)) const uint32_t fx_z63_activation_count=%du;\n'%len(rows))
