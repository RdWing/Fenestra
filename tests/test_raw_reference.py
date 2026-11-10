from pathlib import Path
import struct,subprocess,sys,tempfile,unittest
import errno,os
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from raw_reference import boxes,frame,inspect
from log3g10_reference import reference
from rewrap_r3d_reference import convert,publish,rewrite
ROOT=Path(__file__).resolve().parents[1]

def bx(k,p):return struct.pack('>I4s',8+len(p),k)+p

def movie(nctg=b''):
    mat=bytes.fromhex('003f1b090e3ec335e2bd152ea63e69b76a3f862ffebe8d9bac3bcd1418be3139d23fa0c065')
    packet=bx(b'NRAW',bx(b'NRFH',bx(b'NRMT',struct.pack('>I',0x1900012)+mat))+b'\xff\x10TEST\xff\x11')
    def moov(offset):
        stbl=bx(b'stsz',struct.pack('>III',0,len(packet),1))
        stbl+=bx(b'stsc',struct.pack('>IIIII',0,1,1,1,1))
        stbl+=bx(b'stco',struct.pack('>III',0,1,offset))
        stbl+=bx(b'stsd',struct.pack('>II',0,1)+bx(b'NRAW',bytes(78)))
        mdia=bx(b'hdlr',bytes(8)+b'vide'+bytes(12))+bx(b'minf',bx(b'stbl',stbl))
        return bx(b'moov',bx(b'trak',bx(b'mdia',mdia))+bx(b'udta',bx(b'NCDT',bx(b'NCTG',nctg))))
    prefix=bx(b'ftyp',b'niko'+bytes(4));m=moov(0);m=moov(len(prefix)+len(m)+8)
    return prefix+m+bx(b'mdat',packet)

class RawReferenceTests(unittest.TestCase):
    def test_stock_matrix_changes_only_sample_description(self):
        source=movie();changed=rewrite(source,'stock')
        at=source.index(b'NRAW')
        self.assertEqual(changed,source[:at]+b'NR3D'+source[at+4:])
    def test_missing_gamma_tags_and_invalid_layouts(self):
        with self.assertRaisesRegex(ValueError,'missing gamma tags'):rewrite(movie(),'zr',True)
        data=movie()
        for end in (1,7,len(data)-1):
            with self.subTest(end=end),self.assertRaises(ValueError):rewrite(data[:end])
        with self.assertRaisesRegex(ValueError,'one RAW video'):rewrite(data.replace(b'vide',b'soun',1))
        with self.assertRaisesRegex(ValueError,'missing or invalid RAW matrix'):
            rewrite(data.replace(b'\x01\x90\x00\x12',b'\x01\x90\x00\x13'))
        with self.assertRaisesRegex(ValueError,'unsupported RAW sample description'):
            rewrite(data.replace(b'NRAW',b'apch',1))
        with self.assertRaisesRegex(ValueError,'fragmented'):
            rewrite(data+bx(b'moof',b''))
    def test_nctg_rejects_duplicate_truncated_and_unknown_fields(self):
        entry=struct.pack('>IHHH',0x21,3,1,1)
        for value in (b'A',entry+entry,struct.pack('>IHH',0x21,99,1),entry[:-1]):
            with self.subTest(value=value),self.assertRaises(ValueError):rewrite(movie(value))
    def test_gamma_ablation_keeps_sizes_and_source(self):
        entries=b''.join(struct.pack('>IHHH',key,3,1,1) for key in (0x21,0x26,0x27))
        entries+=struct.pack('>IHH',0x2000023,1,108)+bytes(108)
        source=movie(entries);out=rewrite(source,'stock',True)
        self.assertEqual(len(out),len(source))
        self.assertEqual(out.count(b'RWGLOG3G10'),2)
        self.assertEqual(source,movie(entries))
    def test_failed_write_and_short_write_remove_temporary(self):
        original_fdopen=os.fdopen
        for short in (False,True):
            class FailingStream:
                def __init__(self,fd,mode):self.stream=original_fdopen(fd,mode)
                def __enter__(self):return self
                def __exit__(self,*args):self.stream.close()
                def write(self,data):
                    if short:return self.stream.write(data[:-1])
                    raise OSError(errno.ENOSPC,'simulated full storage')
            with self.subTest(short=short),tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/'new.R3D'
                with patch('rewrap_r3d_reference.os.fdopen',FailingStream),self.assertRaises(OSError):
                    publish(output,b'complete output')
                self.assertEqual(list(Path(tmp).iterdir()),[])
    def test_finalization_failure_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'new.R3D'
            with patch('rewrap_r3d_reference.os.fsync',side_effect=OSError(errno.ENOSPC,'simulated flush failure')):
                with self.assertRaises(OSError):publish(output,b'complete output')
            self.assertEqual(list(Path(tmp).iterdir()),[])
            output.write_bytes(b'keep this file')
            with self.assertRaises(FileExistsError):publish(output,b'new output')
            self.assertEqual(output.read_bytes(),b'keep this file')
            self.assertEqual(list(Path(tmp).iterdir()),[output])
    def test_minimal_round_trip_preserves_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'input.NEV';b=Path(tmp)/'new.R3D';a.write_bytes(movie())
            subprocess.run([sys.executable,str(ROOT/'host/rewrap_r3d_reference.py'),str(a),str(b)],check=True,capture_output=True)
            left,right=inspect(a),inspect(b)
            self.assertEqual(left['video'][0]['codestream'],right['video'][0]['codestream'])
            self.assertNotEqual(left['video'][0]['tags'],right['video'][0]['tags'])
            self.assertEqual(right['video'][0]['tags']['0x1900012'],reference()['matrix_hex'])
            self.assertIn(b'NR3D',b.read_bytes());self.assertEqual(a.read_bytes(),movie())
            before=b.read_bytes()
            again=subprocess.run([sys.executable,str(ROOT/'host/rewrap_r3d_reference.py'),str(a),str(b)],capture_output=True)
            self.assertNotEqual(again.returncode,0);self.assertEqual(b.read_bytes(),before)
    def test_invalid_box_sizes(self):
        for data in (b'123',struct.pack('>I4s',7,b'bad!'),struct.pack('>I4s',100,b'bad!'),struct.pack('>I4s',1,b'bad!')):
            with self.assertRaises(ValueError):list(boxes(data,0,len(data)))
    def test_missing_or_duplicate_frame_tags(self):
        p=bx(b'NRAW',bx(b'NRFH',bx(b'NRMT',b'\x01\x90\x00\x12')))
        with self.assertRaises(ValueError):frame(p,0,len(p))
        tag=bx(b'NRMT',b'\x01\x90\x00\x12\0')
        p=bx(b'NRAW',bx(b'NRFH',tag+tag)+b'\xff\x10TEST')
        with self.assertRaises(ValueError):frame(p,0,len(p))
