import copy
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
from check_z63_nor_audit import audit


class NorAuditTests(unittest.TestCase):
    def trace(self,events,complete=True):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nor.txt'
            lines=['FXNOR1 synthetic controller fixture']
            for i,(kind,at,value) in enumerate(events):
                lines.append(f'{i} 0 {kind} a02bdecd0 {at:x} 4 {value:x} 1')
            if complete:lines.append(f'END {len(events)}')
            path.write_text('\n'.join(lines)+'\n')
            return audit(path)

    def test_every_operation_and_completion_is_required(self):
        # More than the older emulator's sampled log limit, including a
        # program on every iteration rather than every 256th program.
        events=[]
        for i in range(40):
            offset=0x5e20000+i*256
            events += [('W',0xe007094,0x5e20000),('W',0xe007090,0xdc0b0001),
                       ('W',0xe007090,0x05930401),('R',0xe0070a0,1),('R',0xe0070a0,0),
                       ('W',0xe00701c,offset),('W',0xe007078,offset),('W',0xe00707c,4),
                       ('W',0xe007070,1),('W',0x40000000+offset,0x12345678),('R',0xe007070,0x20)]
        result=self.trace(events)
        self.assertEqual((result['erases'],result['programs'],result['nor_stores']),(40,40,40))
        with self.assertRaises(ValueError):self.trace(events,False)
        with self.assertRaises(ValueError):self.trace(events[:-1])
        invalid=copy.copy(events);invalid[9]=('W',0x401a0000,0)
        with self.assertRaises(ValueError):self.trace(invalid)
        invalid=copy.copy(events);invalid[0]=('W',0xe007094,0)
        with self.assertRaises(ValueError):self.trace(invalid)
        invalid=copy.copy(events);invalid.pop(9)
        with self.assertRaises(ValueError):self.trace(invalid)
