from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'host'))
from inspect_recording_color import color_record, hevc_configuration, hevc_sample, inspect_data, prores_header


def box(kind, payload):
    return struct.pack('>I4s', len(payload)+8, kind) + payload


def prores(color=(1, 1, 1)):
    packet = bytearray(28)
    struct.pack_into('>I4sH', packet, 0, len(packet), b'icpf', 20)
    packet[22:25] = bytes(color)
    return bytes(packet)


def movie(packets, colors=None):
    colr = b'' if colors is None else box(b'colr', colors)
    def moov(offset):
        stbl = box(b'stsd', struct.pack('>II', 0, 1) + box(b'apch', bytes(78)+colr))
        stbl += box(b'stsz', struct.pack('>III', 0, 0, len(packets)) +
                    b''.join(struct.pack('>I', len(p)) for p in packets))
        stbl += box(b'stsc', struct.pack('>IIIII', 0, 1, 1, len(packets), 1))
        stbl += box(b'stco', struct.pack('>III', 0, 1, offset))
        mdia = box(b'hdlr', bytes(8)+b'vide'+bytes(12)) + box(b'minf', box(b'stbl', stbl))
        return box(b'moov', box(b'trak', box(b'mdia', mdia)))
    prefix = moov(0)
    return moov(len(prefix)+8) + box(b'mdat', b''.join(packets))


class RecordingColorTests(unittest.TestCase):
    def test_separate_container_and_every_frame(self):
        data = movie([prores(), prores((9, 2, 1)), prores()], b'nclc'+struct.pack('>HHH', 1, 1, 1))
        row = inspect_data(data)[0]
        self.assertEqual(row['frames'], 3)
        self.assertEqual(row['container_color']['transfer'], 1)
        self.assertEqual(row['prores_colors'], [
            dict(primaries=1, transfer=1, matrix=1, frames=2),
            dict(primaries=9, transfer=2, matrix=1, frames=1)])

    def test_missing_color_does_not_invent_a_default(self):
        self.assertIsNone(inspect_data(movie([prores()]))[0]['container_color'])

    def test_color_record_bounds_and_range(self):
        self.assertTrue(color_record(b'nclx'+struct.pack('>HHH', 2, 2, 1)+b'\x80')['full_range'])
        for data in (b'nclc', b'nclx'+bytes(6), b'nclc'+bytes(7), b'nclx'+bytes(6)+b'\x81'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                color_record(data)

    def test_bad_prores_header_and_size(self):
        bad_size = bytearray(prores())
        bad_size[3] += 1
        bad_header = bytearray(prores())
        bad_header[9] = 21
        for packet in (b'icpf', bad_size, bad_header, prores()[:-1]):
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                prores_header(packet)

    def test_sample_outside_media_box(self):
        data = bytearray(movie([prores()]))
        at = data.index(b'stco') + 12
        struct.pack_into('>I', data, at, 0)
        with self.assertRaisesRegex(ValueError, 'outside media'):
            inspect_data(data)

    def test_truncated_movie(self):
        data = movie([prores()])
        for end in (1, 7, len(data)-1):
            with self.subTest(end=end), self.assertRaises(ValueError):
                inspect_data(data[:end])

    def test_fragmented_and_hybrid_movies_are_rejected(self):
        data = movie([prores()])
        with self.assertRaisesRegex(ValueError, 'fragmented'):
            inspect_data(data+box(b'moof', b''))
        size = int.from_bytes(data[:4], 'big')
        with self.assertRaisesRegex(ValueError, 'fragmented'):
            inspect_data(box(b'moov', data[8:size]+box(b'mvex', b''))+data[size:])

    def test_hevc_configuration_and_packet_framing(self):
        config = bytearray(23)
        config[0], config[21], config[22] = 1, 3, 1
        nal = b'\x42\x01ABC'
        config += b'\xa1\0\1'+struct.pack('>H', len(nal))+nal
        length, arrays = hevc_configuration(config)
        self.assertEqual(length, 4)
        self.assertEqual(arrays[0]['type'], 33)
        packet = struct.pack('>I', len(nal))+nal
        self.assertEqual(hevc_sample(packet+packet, length), {33: 2})
        for data in (config[:-1], config+b'\0', config[:22]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                hevc_configuration(data)
        for nal in (b'\xc2\x01ABC', b'\x42\0ABC'):
            with self.subTest(nal=nal), self.assertRaises(ValueError):
                hevc_configuration(config[:-5]+nal)
        for data in (b'', packet[:-1], b'\0\0\0\1\x42', b'\0\0\0\2\x42\0'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                hevc_sample(data, length)


if __name__ == '__main__':
    unittest.main()
