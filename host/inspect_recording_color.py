"""Inspect container and codec color declarations without changing the movie.

The file fields describe decoder inputs. They do not prove the pixel transform.
ProRes offsets follow FFmpeg libavcodec/proresdec2.c (decode_frame_header).
HEVC syntax interpretation uses FFmpeg trace_headers, recorded as separate evidence.
"""
import argparse
from collections import Counter
import hashlib
import json
import mmap
from pathlib import Path
import re
import struct
import subprocess

from raw_reference import boxes, one, samples, movie_bounds


def color_record(data):
    if len(data) not in (10, 11) or data[:4] not in (b'nclc', b'nclx'):
        raise ValueError('unsupported color record')
    expected = 11 if data[:4] == b'nclx' else 10
    if len(data) != expected or (expected == 11 and data[10] & 127):
        raise ValueError('invalid color record')
    return dict(type=data[:4].decode(), primaries=int.from_bytes(data[4:6], 'big'),
                transfer=int.from_bytes(data[6:8], 'big'),
                matrix=int.from_bytes(data[8:10], 'big'),
                full_range=bool(data[10] & 128) if expected == 11 else None)


def prores_header(data):
    if len(data) < 28 or data[4:8] != b'icpf':
        raise ValueError('invalid ProRes frame')
    if int.from_bytes(data[:4], 'big') != len(data):
        raise ValueError('invalid ProRes frame size')
    header_size = int.from_bytes(data[8:10], 'big')
    if not 20 <= header_size <= len(data) - 8:
        raise ValueError('invalid ProRes header size')
    return dict(primaries=data[22], transfer=data[23], matrix=data[24])


def hevc_configuration(data):
    if len(data) < 23 or data[0] != 1:
        raise ValueError('unsupported HEVC configuration')
    length_bytes = (data[21] & 3) + 1
    if length_bytes == 3:
        raise ValueError('reserved HEVC NAL length')
    pos = 23
    arrays = []
    for _ in range(data[22]):
        if len(data) - pos < 3:
            raise ValueError('truncated HEVC array')
        kind = data[pos] & 63
        count = int.from_bytes(data[pos+1:pos+3], 'big')
        pos += 3
        for _ in range(count):
            if len(data) - pos < 2:
                raise ValueError('truncated HEVC NAL size')
            size = int.from_bytes(data[pos:pos+2], 'big')
            pos += 2
            nal = data[pos:pos+size]
            if size < 2 or len(nal) != size or (nal[0] >> 1) & 63 != kind:
                raise ValueError('invalid HEVC configuration NAL')
            if nal[0] & 128 or not nal[1] & 7:
                raise ValueError('invalid HEVC configuration NAL header')
            arrays.append(dict(type=kind, bytes=size, sha256=hashlib.sha256(nal).hexdigest()))
            pos += size
    if pos != len(data):
        raise ValueError('trailing HEVC configuration data')
    return length_bytes, arrays


def hevc_sample(data, length_bytes):
    pos = 0
    result = Counter()
    while pos < len(data):
        if len(data) - pos < length_bytes:
            raise ValueError('truncated HEVC sample length')
        size = int.from_bytes(data[pos:pos+length_bytes], 'big')
        pos += length_bytes
        if size < 2 or size > len(data) - pos:
            raise ValueError('invalid HEVC sample NAL size')
        if data[pos] & 128 or not data[pos+1] & 7:
            raise ValueError('invalid HEVC NAL header')
        result[(data[pos] >> 1) & 63] += 1
        pos += size
    if not result:
        raise ValueError('empty HEVC sample')
    return result


def inspect_data(data):
    moov, media = movie_bounds(data)
    result = []
    for kind, a, b in boxes(data, *moov):
        if kind != b'trak':
            continue
        track = (a, b)
        mdia = one(data, a, b, b'mdia')
        h, end = one(data, *mdia, b'hdlr')
        if end-h < 12:
            raise ValueError('truncated media handler')
        if data[h+8:h+12] != b'vide':
            continue
        a, b = one(data, *mdia, b'minf')
        a, b = one(data, a, b, b'stbl')
        a, b = one(data, a, b, b'stsd')
        if b-a < 8 or data[a:a+8] != b'\0\0\0\0\0\0\0\1':
            raise ValueError('unsupported sample descriptions')
        entries = list(boxes(data, a+8, b))
        if len(entries) != 1:
            raise ValueError('invalid sample description count')
        codec, a, b = entries[0]
        if codec not in (b'hvc1', b'hev1', b'apch', b'apcn', b'apcs', b'apco'):
            raise ValueError('unsupported video codec')
        if b-a < 78:
            raise ValueError('truncated visual sample entry')
        child = list(boxes(data, a+78, b))
        colors = [color_record(data[x:y]) for k, x, y in child if k == b'colr']
        if len(colors) > 1:
            raise ValueError('duplicate container color')
        row = dict(codec=codec.decode(), container_color=colors[0] if colors else None)
        length_bytes = None
        if codec in (b'hvc1', b'hev1'):
            configurations = [(x, y) for k, x, y in child if k == b'hvcC']
            if len(configurations) != 1:
                raise ValueError('missing or duplicate HEVC configuration')
            x, y = configurations[0]
            length_bytes, row['parameter_sets'] = hevc_configuration(data[x:y])
        packet_colors = Counter()
        nal_types = Counter()
        all_samples = samples(data, track)
        for offset, size in all_samples:
            if not any(x <= offset and offset+size <= y for x, y in media):
                raise ValueError('sample outside media box')
            packet = data[offset:offset+size]
            if length_bytes is None:
                packet_colors[tuple(prores_header(packet).values())] += 1
            else:
                nal_types.update(hevc_sample(packet, length_bytes))
        if not all_samples:
            raise ValueError('missing video samples')
        row['frames'] = len(all_samples)
        row['prores_colors'] = [dict(primaries=k[0], transfer=k[1], matrix=k[2], frames=n)
                                for k, n in sorted(packet_colors.items())]
        row['hevc_nal_counts'] = dict(sorted(nal_types.items()))
        result.append(row)
    if not result:
        raise ValueError('missing video track')
    return result


def external_fields(path, hevc):
    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,pix_fmt,color_space,color_transfer,color_primaries,color_range',
        '-of', 'json', str(path)], check=True, capture_output=True, text=True)
    nikon = subprocess.run(['exiftool', '-j', '-Model', '-Software', '-PictureControlName',
        '-PictureControlBase', str(path)], check=True, capture_output=True, text=True)
    result = dict(ffprobe=json.loads(probe.stdout), nikon=json.loads(nikon.stdout)[0])
    result['nikon'].pop('SourceFile', None)
    if hevc:
        trace = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'trace', '-i', str(path),
            '-map', '0:v:0', '-c:v', 'copy', '-an', '-bsf:v', 'trace_headers',
            '-frames:v', '1', '-f', 'null', '-'], check=True, capture_output=True, text=True)
        names = ('video_signal_type_present_flag', 'video_full_range_flag',
                 'colour_description_present_flag', 'colour_primaries',
                 'transfer_characteristics', 'matrix_coefficients')
        fields = {name: sorted(set(int(v) for v in re.findall(
            r'\b' + name + r'\s+[01]+\s+=\s+(\d+)', trace.stderr))) for name in names}
        result['ffmpeg_first_frame_vui'] = fields
        result['ffmpeg_trace_sha256'] = hashlib.sha256(trace.stderr.encode()).hexdigest()
    result['tool_versions'] = {}
    for tool, arg in [('ffmpeg', '-version'), ('ffprobe', '-version'), ('exiftool', '-ver')]:
        version = subprocess.run([tool, arg], check=True, capture_output=True, text=True)
        result['tool_versions'][tool] = version.stdout.splitlines()[0]
    return result


def inspect(path, with_tools=False):
    path = Path(path)
    with path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        result = dict(schema=1, source_bytes=len(data), source_sha256=hashlib.sha256(data).hexdigest(),
                      tracks=inspect_data(data))
    if with_tools:
        if len(result['tracks']) != 1:
            raise ValueError('external inspection requires one video track')
        result['external'] = external_fields(path, any(
            row['codec'] in ('hvc1', 'hev1') for row in result['tracks']))
    result['scope'] = 'File declarations and sample framing only. No pixel transform or color accuracy claim.'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('movie', type=Path)
    parser.add_argument('--tools', action='store_true', help='Read FFmpeg and ExifTool fields too.')
    args = parser.parse_args()
    print(json.dumps(inspect(args.movie, args.tools), indent=2))
