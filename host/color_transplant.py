"""Build and call the isolated color candidate on the host."""
import ctypes
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
PARAMETERS=0x408
SAMPLES=0x2a8e
SIZE=PARAMETERS+SAMPLES
OFFSETS=(0xbe6,0xdb0,0xf7a,0x1144,0x130e,0x14d8)


def library(directory):
    binary=Path(directory)/'color-transplant.dylib'
    subprocess.run(['clang','-shared','-fPIC','-O2','-std=c11','-Wall','-Wextra','-Werror',
        '-Wconversion','-Wshadow','-I',str(ROOT/'include'),
        str(ROOT/'src/platform/z63_c201/color_transplant.c'),str(ROOT/'src/memory.c'),'-o',str(binary)],check=True)
    lib=ctypes.CDLL(str(binary));fn=lib.fx_z63_color_transplant
    fn.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,
                 ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint16]
    fn.restype=ctypes.c_int
    return lib,fn

