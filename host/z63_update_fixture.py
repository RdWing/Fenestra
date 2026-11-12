"""Supply updater admission to a paused disposable QEMU instance over its UDS.

This is a state fixture, not execution of Nikon's updater. The actual admission
instructions are covered separately. Only a verified clean arbitration word is
changed; no feature code, file, flash or physical camera is written.
"""
import socket
from z63_activation import CONTROL_RAM


def claim_update(path):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5);connection.connect(str(path))
        def receive_byte():
            data=connection.recv(1)
            if not data:raise RuntimeError('GDB fixture connection closed')
            return data
        def request(text):
            data=text.encode();connection.sendall(b'$'+data+b'#'+f'{sum(data)&255:02x}'.encode())
            while True:
                start=receive_byte()
                if start==b'-':raise RuntimeError('GDB fixture packet rejected')
                if start!=b'$':continue
                result=bytearray()
                while True:
                    value=receive_byte()
                    if value==b'#':break
                    result+=value
                checksum=receive_byte()+receive_byte()
                if int(checksum,16)!=sum(result)&255:raise RuntimeError('GDB fixture checksum differs')
                connection.sendall(b'+')
                if result.startswith((b'T',b'S')):continue
                return bytes(result)
        if request('Qqemu.PhyMemMode:1')!=b'OK':raise RuntimeError('physical QEMU memory access unavailable')
        if request(f'm{CONTROL_RAM:x},4')!=b'00000000':raise RuntimeError('updater fixture requires a clean session')
        if request(f'M{CONTROL_RAM:x},4:02000000')!=b'OK':raise RuntimeError('updater fixture write failed')
        if request(f'm{CONTROL_RAM:x},4')!=b'02000000':raise RuntimeError('updater fixture readback differs')
    return dict(method='GDB physical memory in a paused disposable QEMU instance',address=hex(CONTROL_RAM),
                before=0,after=2,original_updater_executed=False,physical_camera_accessed=False)
