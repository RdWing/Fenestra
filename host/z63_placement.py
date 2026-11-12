"""Check that resident code is placed where original startup leaves it.

Original C2.01 startup first runs MAIN text in place. It then copies the
content of each text window to DRAM and remaps the whole window to that copy.
Package bytes after a window's copy end are therefore replaced by DRAM the copy
never wrote. An all-zero region in the image is not evidence that it is free.
"""
import hashlib
import struct
import binascii


def constants(code):
    """Return every value a MOVZ/MOVN/MOVK/MOV-register sequence builds."""
    registers, seen = {}, set()
    for (word,) in struct.iter_unpack('<I', code[:len(code) & ~3]):
        rd, wide = word & 31, word >> 31
        mask = (1 << (64 if wide else 32)) - 1
        kind = word & 0x7f800000
        if kind in (0x52800000, 0x12800000, 0x72800000):
            shift = ((word >> 21) & 3) * 16
            value = ((word >> 5) & 0xffff) << shift
            if kind == 0x52800000:
                registers[rd] = value
            elif kind == 0x12800000:
                registers[rd] = ~value & mask
            else:
                registers[rd] = (registers.get(rd, 0) & ~(0xffff << shift) | value) & mask
        elif word & 0x7fe0ffe0 == 0x2a0003e0:
            source = registers.get((word >> 16) & 31)
            if source is None:
                registers.pop(rd, None)
                continue
            registers[rd] = source & mask
        else:
            continue
        seen.add(registers[rd])
    return seen


def check(profile, original):
    """Raise unless the code region survives original text relocation."""
    base = profile['image_base']
    late = profile.get('late_initialization')
    if late and profile.get('target') == 'z63-c201':
        expected = dict(descriptor_slot=0xa02912e60, original_descriptor=0xa028d5590,
                        state_min=0xa00000000, state_max=0xa40000000-80,
                        state_magic=0x465a634d, state_magic_offset=64, bootstrap_event=20)
        if late != expected:
            raise ValueError('late initialization binding differs from C2.01')
        offset = 0x5095000 + late['descriptor_slot']-0xa02808000
        if struct.unpack_from('<Q', original, offset)[0] != late['original_descriptor']:
            raise ValueError('original late-initialization descriptor differs')
    begin, end = (profile['probe_code_region'][name] for name in ('begin', 'end'))
    relocation = profile.get('text_relocation')
    if not relocation or not relocation.get('windows') or not relocation.get('routines'):
        raise ValueError('target has no traced text relocation; code placement is unproven')
    built = set()
    for routine in relocation['routines']:
        at = routine['address'] - base
        code = original[at:at + routine['bytes']]
        if hashlib.sha256(code).hexdigest() != routine['sha256']:
            raise ValueError('text relocation routine differs')
        built |= constants(code)
    for window in relocation['windows']:
        if not window['begin'] <= window['copy_end'] <= window['remap_end']:
            raise ValueError('invalid text window: ' + window['name'])
        # The profile may not assert bounds the original code does not build.
        if window['begin'] not in built or window['copy_end'] not in built:
            raise ValueError('text window bounds are not in the original routine: ' + window['name'])
        length = window['remap_end'] - window['begin']
        if window['remap_end'] != window['copy_end'] and length not in built:
            raise ValueError('text window remap length is not in the original routine: ' + window['name'])
        if begin < window['remap_end'] and window['begin'] < end:
            raise ValueError('code region lies in relocated text window ' + window['name'] +
                             '; original startup replaces it')
    kept = relocation['in_place_executable']
    if not kept['begin'] <= begin < end <= kept['end']:
        raise ValueError('code region is outside the in-place executable range')
    if not 0 <= begin - base < end - base <= len(original) or any(original[begin - base:end - base]):
        raise ValueError('code region is not empty in the original image')
    guard = profile.get('guard_region')
    if not guard:
        raise ValueError('target has no guard region; boot hooks would be unguarded')
    g0, g1 = guard['begin'], guard['end']
    if g0 & 7 or g1 & 3 or not g0 < g1:
        raise ValueError('invalid guard region')
    # Guards must travel with original code: inside the copied content of a window.
    if not any(w['begin'] <= g0 and g1 <= w['copy_end'] for w in relocation['windows']):
        raise ValueError('guard region is not inside copied original text')
    if any(original[g0 - base:g1 - base]):
        raise ValueError('guard region is not empty in the original image')
    return dict(code_region=[begin, end], guard_region=[g0, g1], outside_relocated_windows=True,
                windows={w['name']: [w['begin'], w['copy_end'], w['remap_end']] for w in relocation['windows']},
                loader_places_padding_verified=bool(relocation.get('loader_places_padding_verified')),
                physical_install_qualified=bool(relocation.get('physical_install_qualified')))


MARKER = b'FXZ63COR'
GUARD_WORDS = 8

# guard_integrity.S linked at zero. All references are position independent.
# The ARM regression assembles the source independently and checks these bytes.
INTEGRITY_CODE = bytes.fromhex(
    'e92bbca9eb3301a9ed3b02a909423bd5e91b00f9690700102d2540f9ad0000b4'
    'adfddf88bf09007141000054d00500351f060071400300542c1140f90c0300b4'
    '8cfddfc82d1540f99f010debc00400549f0940f2810400542d1940f99f010deb'
    '230400542d1d40f99f010debc80300548d4140b92e4140b9bf010e6b41030054'
    '1f0a0071c10000548d310191adfddf88ad791e12bf05007161020054312940a9'
    '4c815ff82d0d40f99f010debc10100542b1140b910008012ce0400102c164038'
    '8c01104a8c1d0012cd596cb8b021504a3f020aeb43ffff54f003302a10020b4a'
    '0200001430008052e91b40f909421bd5ed3b42a9eb3341a9e92bc4a8c0035fd6'
)
BOOTSTRAP_CODE = bytes.fromhex(
    'f047bfa9102040b91052005170000034f047c1a800000000f047c1a8e007bda9'
    'fe0b00f900000000e00f00f91f2003d5f04702a9300080520000000050000035'
    '00000000e00f40f9fe0b40f9f04742a9ffc30091c0035fd60000000000000000'
    '000000000000000000000000'
)


UPDATE_CODE = bytes.fromhex(
    'f047bea9fe0b00f91000009470010035fe0b40f9f047c2a800000000f047bea9'
    'fe0b00f90900009490000035fe0b40f9f047c2a800000000fe0b40f9f047c2a8'
    '40008052c0035fd6e92bbfa9e901005830fd5f88d00000354a0080522afd1188'
    '91ffff3510008052030000145f3f03d5100a0051297a0bd59f3f03d5e92bc1a8'
    'c0035fd61f2003d50000000000000000'
)

def integrity_prefix(profile, core):
    begin, end = (profile['probe_code_region'][key] for key in ('begin', 'end'))
    if begin & 7 or end & 7 or not 8 <= end-begin <= 0x60000 or len(core) != end-begin:
        raise ValueError('invalid bounded immutable core extent')
    if core[-8:] != MARKER:
        raise ValueError('immutable core marker missing')
    table = []
    for byte in range(256):
        value = byte
        for _ in range(8):
            value = (value >> 1) ^ (0xedb88320 if value & 1 else 0)
        table.append(value)
    assert len(INTEGRITY_CODE) == 256
    late = profile.get('late_initialization', {})
    return (MARKER + INTEGRITY_CODE + struct.pack('<QQII8s', begin, end,
            binascii.crc32(core), 0, MARKER) +
            struct.pack('<4QII', late.get('descriptor_slot', 0), late.get('original_descriptor', 0),
                        late.get('state_min', 0), late.get('state_max', 0), late.get('state_magic', 0), 0) +
            struct.pack('<Q', profile.get('activation', {}).get('latch', 0)) +
            struct.pack('<256I', *table))


def position_independent(word):
    """True unless the instruction reads PC: it may then run at another address."""
    return not ((word & 0x7c000000) == 0x14000000 or (word & 0xff000010) == 0x54000000 or
                (word & 0x7e000000) in (0x34000000, 0x36000000) or
                (word & 0x1f000000) == 0x10000000 or (word & 0x3b000000) == 0x18000000)


def _branch(source, target, link=False):
    delta = target - source
    if delta % 4 or not -(1 << 27) <= delta < (1 << 27):
        raise ValueError('guard branch out of range')
    return (0x94000000 if link else 0x14000000) | ((delta // 4) & 0x3ffffff)


def marker_address(profile):
    return profile['probe_code_region']['end'] - len(MARKER)


def updater_entries(profile, hooks):
    from z63_activation import UPDATE_SITES
    at = profile['guard_region']['begin'] + 8 + len(INTEGRITY_CODE) + 80 + 1024
    if profile.get('late_initialization'):at += len(BOOTSTRAP_CODE)
    at += 48 * len(hooks)
    return {UPDATE_SITES[0][0]: at, UPDATE_SITES[1][0]: at+0x1c}


def guards(profile, original, hooks, core, boot_entry=None, build_identity=bytes(32)):
    """Guard every core entry with bounded marker/whole-reservation CRC32.

    The validator and its expected checksum live in copied original text,
    outside the optional core. CRC32 detects accidental corruption, not hostile
    replacement/authenticity. All GPRs and NZCV survive each guard. No mutable
    cache is used; validation timing remains a qualification gate.
    """
    base = profile['image_base']
    g0, g1 = (profile['guard_region'][name] for name in ('begin', 'end'))
    out = bytearray(integrity_prefix(profile, core))
    bootstrap = None
    if profile.get('late_initialization'):
        if boot_entry is None or not profile['probe_code_region']['begin'] <= boot_entry < profile['probe_code_region']['end']-8:
            raise ValueError('late initialization requires an in-core post-start entry')
        bootstrap = g0 + len(out)
        out += BOOTSTRAP_CODE
    table = {}
    video_hooks = {row['address']: row for row in profile.get('video_quality', {}).get('hooks', [])}
    activation = profile.get('activation')
    for site in sorted(hooks):
        target, call = hooks[site]
        stub = g0 + len(out)
        word = struct.unpack_from('<I', original, site - base)[0]
        tail = video_hooks.get(site, {}).get('tail', False)
        if call or tail:
            if word >> 26 != (0x25 if call else 5) or (call and tail):
                raise ValueError('original call or tail branch opcode differs')
            delta = word & 0x3ffffff
            callee = site + ((delta - (1 << 26) if delta & (1 << 25) else delta) * 4)
        elif not position_independent(word):
            raise ValueError('hook site instruction cannot be displaced')
        # Save scratch registers and the incoming link before BL validation.
        # CBNZ does not disturb restored NZCV. Both exits restore the exact SP.
        mode = 2 if activation and site not in activation['permanent'] else 0
        words = [0xa9be47f0, 0xf9000bfe, 0x52800010 | mode << 5, _branch(stub+12,g0+8,True),
                 0x35000090, 0xf9400bfe, 0xa8c247f0, _branch(stub+28,target),
                 0xf9400bfe, 0xa8c247f0]
        words += ([_branch(stub+40,callee),0xd4200000] if call or tail else
                  [word,_branch(stub+44,site+4)])
        out += struct.pack('<12I', *words)
        table[site] = stub
    if bootstrap is not None:
        site = profile['sysctl']['dispatcher']
        if site not in table:raise ValueError('late bootstrap requires dispatcher hook')
        normal = table[site]
        offset = bootstrap-g0
        for at, target, call in ((0x14,normal,False),(0x24,bootstrap+0x58,True),
                                  (0x38,g0+8,True),(0x40,boot_entry,True)):
            struct.pack_into('<I',out,offset+at,_branch(bootstrap+at,target,call))
        # The original dispatcher prologue is independent of the optional core.
        prologue = original[site-base:site-base+16]
        if len(prologue)!=16 or any(w&0x3a000000!=0x28000000 for (w,) in struct.iter_unpack('<I',prologue)):
            raise ValueError('unsupported stock bootstrap prologue')
        out[offset+0x58:offset+0x68] = prologue
        struct.pack_into('<I',out,offset+0x68,_branch(bootstrap+0x68,site+16))
        table[site] = bootstrap
    if activation:
        from z63_activation import CONTROL, CONTROL_RAM, UPDATE_SITES
        if activation != dict(control=CONTROL, latch=CONTROL_RAM,
                              permanent=activation['permanent']):
            raise ValueError('activation layout differs')
        update = g0 + len(out)
        code = bytearray(UPDATE_CODE)
        for offset, (site, stock) in zip((0x18, 0x34), UPDATE_SITES):
            if struct.unpack_from('<I', original, site-base)[0] != _branch(site, stock):
                raise ValueError('updater admission preimage differs')
            struct.pack_into('<I', code, offset, _branch(update+offset, stock))
        struct.pack_into('<Q', code, len(UPDATE_CODE)-8, CONTROL_RAM)
        out += code
        if g0 + len(out) > CONTROL:
            raise ValueError('activation guard reservation exhausted')
        out += bytes(g1-g0-len(out))
    if g0 + len(out) > g1:
        raise ValueError('guard region exhausted')
    return bytes(out), table
