"""Offline minimal R3D compatibility reference. Compressed RAW samples stay unchanged."""
import argparse
import json
import os
from pathlib import Path
import struct
import tempfile
from raw_reference import boxes, one, samples, frame, movie_bounds
from r3dne_profile import load as load_raw_profile


def rewrite(source, matrix_mode='zr', rewrite_gamma_tags=False):
    if matrix_mode not in ('stock', 'zr'):
        raise ValueError('unsupported matrix selection')
    data = bytearray(source)
    (ma, mb), media = movie_bounds(data)
    video_tracks = []
    for kind, a, b in boxes(data, ma, mb):
        if kind != b'trak':
            continue
        x, y = one(data, a, b, b'mdia')
        h, end = one(data, x, y, b'hdlr')
        if end-h < 12:
            raise ValueError('truncated media handler')
        if data[h+8:h+12] == b'vide':
            video_tracks.append((a, b))
    if len(video_tracks) != 1:
        raise ValueError('one RAW video track required')
    track = video_tracks[0]
    x, y = one(data, *track, b'mdia')
    x, y = one(data, x, y, b'minf')
    x, y = one(data, x, y, b'stbl')
    x, y = one(data, x, y, b'stsd')
    if y-x < 8 or data[x:x+8] != b'\0\0\0\0\0\0\0\1':
        raise ValueError('one RAW sample description required')
    descriptions = list(boxes(data, x+8, y))
    if len(descriptions) != 1 or descriptions[0][0] != b'NRAW' or descriptions[0][2]-descriptions[0][1] < 78:
        raise ValueError('unsupported RAW sample description')
    data[x+12:x+16] = b'NR3D'
    _, matrix = load_raw_profile()
    packets = samples(data, track)
    if not packets:
        raise ValueError('missing RAW frames')
    for offset, size in packets:
        if not any(a <= offset and offset+size <= b for a, b in media):
            raise ValueError('RAW sample outside media box')
        _, tags = frame(data, offset, size)
        if 0x1900012 not in tags or tags[0x1900012][1] != 37:
            raise ValueError('missing or invalid RAW matrix')
        address, _ = tags[0x1900012]
        if matrix_mode == 'zr':
            data[address:address+37] = matrix
        # Dynamic RED/profile fields stay with their original frame producers.
    a, b = one(data, ma, mb, b'udta')
    a, b = one(data, a, b, b'NCDT')
    a, b = one(data, a, b, b'NCTG')
    units = (1, 1, 1, 2, 4, 8, 1, 1, 2, 4, 8, 4, 8)
    seen = set()
    pos = a
    while pos < b:
        if b-pos < 8:
            raise ValueError('truncated NCTG entry')
        key, value_type, count = struct.unpack_from('>IHH', data, pos)
        if value_type >= len(units):
            raise ValueError('unsupported NCTG type')
        if key in seen:
            raise ValueError('duplicate NCTG key')
        seen.add(key)
        size, value = units[value_type]*count, pos+8
        if size > b-value:
            raise ValueError('NCTG entry exceeds box')
        if rewrite_gamma_tags and key in (0x21, 0x26, 0x27):
            if size != 2:
                raise ValueError('invalid gamma tag size')
            data[value:value+2] = struct.pack('>H', {0x21: 65, 0x26: 4, 0x27: 3}[key])
        if rewrite_gamma_tags and key == 0x2000023:
            if size < 50:
                raise ValueError('short Picture Control metadata')
            for offset in (8, 28):
                data[value+offset:value+offset+20] = b'RWGLOG3G10'.ljust(20, b'\0')
            data[value+49] = 3
        pos = value+size
    if rewrite_gamma_tags and not {0x21, 0x26, 0x27, 0x2000023}.issubset(seen):
        raise ValueError('missing gamma tags')
    return data


def publish(output, data):
    """Publish after write and fsync. A failure leaves no partial destination."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.r3d-reference-', dir=output.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            if stream.write(data) != len(data):
                raise OSError('short reference write')
            stream.flush()
            os.fsync(stream.fileno())
        # The link operation refuses an existing destination, including a race.
        os.link(temporary, output)
    finally:
        os.unlink(temporary)


def convert(source, output, matrix_mode='zr', rewrite_gamma_tags=False):
    source, output = Path(source), Path(output)
    if output.exists() or source.resolve() == output.resolve():
        raise ValueError('new output path required')
    data = rewrite(source.read_bytes(), matrix_mode, rewrite_gamma_tags)
    publish(output, data)
    return dict(output=str(output), matrix=matrix_mode, gamma_tags_rewritten=rewrite_gamma_tags,
                camera_qualification=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--matrix', choices=('stock', 'zr'), default='zr')
    parser.add_argument('--rewrite-gamma-tags', action='store_true')
    args = parser.parse_args()
    print(json.dumps(convert(args.source, args.output, args.matrix, args.rewrite_gamma_tags)))
