# SPDX-License-Identifier: MIT
"""Read C2.01 movie request rows and initializer states from a pinned MAIN.

This checks menu requests, not effective settings or encoder admission.
It needs no camera, emulator, private corpus, or third-party Python package.
The state-block check adapts trace_z6iii_video_file_settings.py (MIT).
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

SHA256 = '236bbd874e0942fd91fb54a99af456f4ebcc0fd966af930753c43efd1839fe87'
BASE = 0x40160000
BYTES = 88830365
FORMATS = {1: 'H.264 8-bit', 2: 'H.265 8-bit', 3: 'H.265 10-bit',
           4: 'ProRes 422 HQ 10-bit', 5: 'ProRes RAW HQ 12-bit', 6: 'N-RAW 12-bit'}
PTP_ARRAYS = {1: (0xA029A5CB0, 8), 2: (0xA029A5C08, 21), 3: (0xA029A5C08, 21),
              4: (0xA029A5BA8, 12), 5: (0xA029A5D78, 13), 6: (0xA029A5CF0, 17)}


def check(path):
    data = Path(path).read_bytes()
    if len(data) != BYTES or hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('C2.01 MAIN identity differs')

    def words(address, count):
        return struct.unpack_from('<'+'I'*count, data, address-BASE)

    def branch_target(pc, instruction):
        if instruction >> 26 != 0b100101:
            raise ValueError('initializer call instruction differs')
        displacement = instruction & 0x3ffffff
        if displacement & 0x2000000:
            displacement -= 0x4000000
        return pc + displacement*4

    # Each original unrolled block obtains a row and requests state one.
    # Decode the instructions rather than infer this set from row labels.
    forced = []
    for pc in range(0x4058F838, 0x4058FC0C, 28):
        op = words(pc, 7)
        if (op[0] & 0xffe0001f != 0x52800001 or
                op[1] != 0xaa1303e0 or op[3] != 0x2a0003e1 or
                op[4] != 0xaa1303e0 or op[5] != 0x52800022):
            raise ValueError('initializer state block differs')
        if (branch_target(pc+8, op[2]), branch_target(pc+24, op[6])) != (0x403c07b8, 0x403c2f78):
            raise ValueError('initializer state helper differs')
        forced.append((op[0] >> 5) & 0xffff)
    if len(set(forced)) != 35:
        raise ValueError('initializer state count differs')
    if words(0x40593918, 1)[0] != 0x0ea00800:
        raise ValueError('size/rate lane swap differs')
    sizes, rates = words(0x42bd2f38, 6), words(0x42bd2f50, 6)
    generic = words(0x42bd1ec0, 3)
    if generic[:2] != (sizes[0], rates[0]):
        raise ValueError('generic request keys differ')
    # The provider selects initialized RAM arrays by requested file type.
    # It does not read tone or image area. Other admission gates remain separate.
    def pairs(address, count):
        return dict(struct.iter_unpack('<II', data[address-BASE:address-BASE+count*8]))
    raster_map = pairs(0x441e4540, 8)
    rate_map = pairs(0x441e4580, 9)
    slow_map = pairs(0x441e45c8, 3)
    if data[0x441e4508-BASE:0x441e450e-BASE] != bytes([0, 6, 6, 23, 12, 18]):
        raise ValueError('PTP provider dispatch differs')
    descriptor = struct.unpack_from('<18Q', data, 0x5232708)
    if (descriptor[0], descriptor[2], descriptor[6]) != (0xd0a0, 0x4088fa70, 0x4088fce0):
        raise ValueError('PTP size descriptor differs')
    lists = []
    for kind, (pointer, count) in PTP_ARRAYS.items():
        offset = pointer - 0xA02808000 + 0x5095000
        raw = data[offset:offset+count*8]
        entries = []
        for index, (wire,) in enumerate(struct.iter_unpack('<Q', raw)):
            values = [raster_map[wire >> 32], rate_map[wire >> 16 & 255]]
            auxiliary_class = wire >> 8 & 63
            if kind == 1:
                values.append(slow_map[wire & 255] if auxiliary_class == 1 else 0)
            entries.append(dict(index=index, wire=f'0x{wire:016X}',
                                width=wire >> 48, height=wire >> 32 & 65535,
                                nominal_rate=wire >> 16 & 255, low_16_bits=wire & 65535,
                                auxiliary_class_bits_8_13=auxiliary_class,
                                auxiliary_value_bits_0_7=wire & 255,
                                request_values=values))
        lists.append(dict(movie_file_type=kind, pointer=hex(pointer), count=count,
                          source_file_offset=hex(offset), initialized_bytes_sha256=hashlib.sha256(raw).hexdigest(),
                          entries=entries))
    rows = []
    for index in range(127):
        address = 0x42bd02dc + index*24
        record = words(address, 6)
        identity, kind, rate, size, slow, _ = record
        if kind not in FORMATS:
            raise ValueError('unknown row file type')
        keys = [sizes[kind-1], rates[kind-1]]
        values = [size, rate]
        if kind == 1:
            keys.append(generic[2])
            values.append(slow)
        rows.append(dict(index=index, address=hex(address), identity=hex(identity),
                         movie_file_type=kind, format=FORMATS[kind], words_u32=list(record),
                         request_keys=[f'0x{key:08X}' for key in keys], request_values=values,
                         ptp_wires_with_matching_request_values=[entry['wire'] for entry in lists[kind-1]['entries']
                                                                 if entry['request_values'] == values],
                         initializer_state_for_matching_file_type=int(identity in forced)))
    if len({row['identity'] for row in rows}) != 127:
        raise ValueError('duplicate row identity')
    if not set(forced) <= {row['words_u32'][0] for row in rows}:
        raise ValueError('initializer identity lacks a request row')
    counts = Counter(row['movie_file_type'] for row in rows)
    state_zero = Counter(row['movie_file_type'] for row in rows
                         if row['initializer_state_for_matching_file_type'] == 0)
    if [counts[k] for k in FORMATS] != [8, 24, 24, 12, 23, 36]:
        raise ValueError('file-type row counts differ')
    if [state_zero[k] for k in FORMATS] != [8, 21, 21, 12, 13, 17]:
        raise ValueError('file-type presentation counts differ')
    return dict(schema=1, firmware_sha256=SHA256, firmware_bytes=BYTES,
                source='Original C2.01 object 280 table and initializer instructions.',
                scope='Request values and presentation states only. No effective settings or encoder admission claim.',
                callback='0x4059377C', initializer='0x4058F68C',
                rows=rows, forced_state_one_identities=[hex(value) for value in forced],
                counts=[dict(movie_file_type=k, stored_rows=counts[k], state_zero_rows=state_zero[k]) for k in FORMATS],
                target_file_types=[3, 4, 5, 6], target_rows=95, target_state_zero_rows=63,
                ptp_size_lists=dict(provider='0x40891174', property='0xD0A0',
                                    descriptor_pointer='0xA029A5708', descriptor_source_file_offset='0x5232708',
                                    selector_key='0x06000F06', arrays=lists,
                                    invalid_file_type_fallback=dict(pointer='0xA029A5C08', count=21),
                                    null_output_returns=0,
                                    setter='0x4088FCE0', validator='0x4088FA70',
                                    boundary='Membership permits the PTP setter request path. It does not establish effective settings or recording admission.',
                                    storage='Initialized RAM projection: file 0x5095000 maps to RAM 0xA02808000. Runtime initialization and later mutation are not executed by this checker.',
                                    validator_conditions=[
                                        'Returns 0x200F when helper 0x408A48E0 bit0 is set and helper 0x408A4864 returns 2.',
                                        'For nonnull payload, key 0x04002C0C values 1 or 3 enter an additional check unless key 0x04002C13 equals 1.',
                                        'That check rejects 5376x3024, 6048x3402, 4032x2268, and 1920x1080 at nominal 200 or 240.',
                                        'Names and producers of these mode conditions, outer dispatch, tone and image-area joins remain unresolved.'],
                                    source_spans=[dict(start=hex(a), end_exclusive=hex(z),
                                                       sha256=hashlib.sha256(data[a-BASE:z-BASE]).hexdigest())
                                                  for a,z in [(0x40891174,0x40891234),(0x4088FA70,0x4088FB80),
                                                              (0x4088FCE0,0x4088FE80),(0x40864C58,0x40864C7C),
                                                              (0x408A5074,0x408A5128)]]),
                limits=['Row states do not prove final widget visibility or encoder admission.',
                        'The callback uses a separately read file type; it does not validate the selected row file type.',
                        'A forced-state menu row can have the same request values as a PTP list entry. The lists contain values, not menu row identities.',
                        'The PTP setter rereads file type for its size and rate keys, and does not check the batch setter result.',
                        'Image area, exact frame rates, quality, proxy policy and processing routes need separate joins.',
                        'No physical recording or Log3G10/RWG color qualification is claimed.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('main', type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.main), indent=2))
