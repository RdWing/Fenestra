import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from wlm_bundle import encode_frontend_bundle,decode_frontend_bundle
from module_header import entry_abi,stack_requirements,validate_package


def frontend():
    body=struct.pack('<6I',0,152,4,4,5,4)+bytes.fromhex('c0035fd6')
    h=bytearray(128);h[:8]=b'FENESTRA'
    struct.pack_into('<4I',h,8,3,128,1,1)
    h[56:88]=hashlib.sha256(body).digest()
    struct.pack_into('<5IQ',h,88,156,4096,0,1,0,0)
    struct.pack_into('<3I',h,116,1,32768,4096)
    return bytes(h)+body


class FrontendBundleTests(unittest.TestCase):
    def test_host_and_c_preparation(self):
        front=frontend();target=bytes(32)
        bundle=encode_frontend_bundle(front,'unit',target)
        self.assertEqual(decode_frontend_bundle(bundle,target,'unit')['frontend'],front)
        self.assertEqual(entry_abi(bundle),1)
        self.assertEqual(stack_requirements(bundle),(32768,4096))
        self.assertEqual(validate_package(bundle,target)['package_bytes'],len(bundle))
        with self.assertRaises(ValueError):decode_frontend_bundle(bundle,target,'other')
        variants=[(bundle,True)]
        for at in (0,8,12,16,20,24,56,88,92,96,100,104,136,140,144,148,152,167,168,191,192+8,192+116,len(bundle)-1):
            bad=bytearray(bundle);bad[at]^=1
            if at==152:bad[at]=255
            with self.subTest(offset=at):
                with self.assertRaises(ValueError):decode_frontend_bundle(bad,target)
            variants.append((bytes(bad),False))
        variants.extend([(bundle[:-1],False),(bundle+b'\0',False)])
        # Rehashed outer contents must not bypass inner entry/body validation.
        for at in (192+8,192+116,len(bundle)-1):
            bad=bytearray(bundle);bad[at]^=1
            bad[56:88]=bad[104:136]=hashlib.sha256(bad[192:]).digest()
            with self.assertRaises(ValueError):decode_frontend_bundle(bad,target)
            variants.append((bytes(bad),False))
        bad=bytearray(bundle)
        struct.pack_into('<Q',bad,192+108,0x80000)
        bad[56:88]=bad[104:136]=hashlib.sha256(bad[192:]).digest()
        with self.assertRaises(ValueError):decode_frontend_bundle(bad,target,capabilities=0)
        variants.append((bytes(bad),False))
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as temp:
            temp=Path(temp);source=temp/'check.c';binary=temp/'check'
            source.write_text(r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fenestra_module.h"
#include "fenestra.h"
#include "fenestra_platform.h"
#include "fenestra_extensions.h"
FxExtensionDomain *fx_native_extensions(FxPlatformOwner *p){(void)p;return 0;}
static unsigned char package[4096];
static uint32_t package_bytes,reads,position,bad_visible;
static FxResult directory_open(void *c){(void)c;position=0;reads=0;return FX_OK;}
static FxResult directory_next(void *c,FxModuleDirectoryEntry *e){
 (void)c;if(position>=2)return FX_EMPTY;
 memset(e,0,sizeof(*e));
 strcpy(e->name,position++?"unit.wlm":bad_visible?"bad name.wlm":"._unit.wlm");
 e->bytes=package_bytes;return FX_OK;
}
static FxResult directory_close(void *c){(void)c;return FX_OK;}
static void *allocate(void *c,uint32_t n){(void)c;return malloc(n);}
static void release(void *c,void *p){(void)c;free(p);}
static FxResult read_package(void *c,const char *name,uint8_t *out,uint32_t cap,uint32_t *n){
 (void)c;++reads;if(name[0]=='.')return FX_INTEGRITY;if(cap<package_bytes)return FX_BOUNDS;
 memcpy(out,package,package_bytes);*n=package_bytes;return FX_OK;
}
static _Alignas(4096) unsigned char image[4096];
int main(int argc,char **argv){
 if(argc!=3)return 10;
 unsigned char target[32]={0},digest[32],scratch[4096];
 FILE *f=fopen(argv[1],"rb");if(!f)return 11;
 size_t n=fread(package,1,sizeof(package),f);fclose(f);package_bytes=(uint32_t)n;
 memset(image,0xa5,sizeof(image));fx_sha256(package,(uint32_t)n,digest);
 FxModule m;FxResult r=fx_module_prepare(package,(uint32_t)n,digest,target,0,image,sizeof(image),&m);
 if(argv[2][0]=='1'){
  if(r || !m.prepared || m.entry_abi!=1 || m.stacks.native_bytes!=32768 || m.stacks.user_bytes!=4096 || memcmp(image,"\xc0\x03\x5f\xd6",4))return 20;
  FxModuleDirectory io={.read=read_package};
  if(fx_module_directory_inspect(&io,"unit.wlm",n,target,0,(FxIndexMemory){0},scratch,sizeof(scratch),&m,digest)!=FX_OK)return 21;
  if(fx_module_directory_inspect(&io,"unit.wlm.disabled",n,target,0,(FxIndexMemory){0},scratch,sizeof(scratch),&m,digest)!=FX_OK)return 22;
  if(fx_module_directory_inspect(&io,"other.wlm",n,target,0,(FxIndexMemory){0},scratch,sizeof(scratch),&m,digest)!=FX_INTEGRITY)return 23;
  io.open=directory_open;io.next=directory_next;io.close=directory_close;
  FxModuleInventory inventory={0};FxIndexMemory memory={0,allocate,release};
  if(fx_modules_discover(&io,target,0,scratch,sizeof(scratch),&inventory,memory)!=FX_OK || inventory.count!=1 || reads!=1)return 24;
  fx_modules_destroy(&inventory);bad_visible=1;
  if(fx_modules_discover(&io,target,0,scratch,sizeof(scratch),&inventory,memory)!=FX_ARGUMENT || inventory.count || reads)return 25;
  return 0;
 }
 for(unsigned i=0;i<sizeof(image);++i)if(image[i]!=0xa5)return 12;
 return r==FX_OK?13:0;
}
''')
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),str(source),str(ROOT/'src/module.c'),str(ROOT/'src/memory.c'),str(ROOT/'src/sha256.c'),*[str(ROOT/'src'/name) for name in ['services.c','platform.c','binding_store.c','native_call.c','accounting.c','extensions.c','stream.c']],'-o',str(binary)],check=True)
            for index,(data,valid) in enumerate(variants):
                path=temp/f'{index}.wlm';path.write_bytes(data)
                with self.subTest(c_case=index):subprocess.run([str(binary),str(path),'1' if valid else '0'],check=True)
