from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class VideoQualityTests(unittest.TestCase):
    def test_prores_app_ui_selection_retry_and_missing_service(self):
        self.check_quality_app([])

    def test_h265_app_mode_refusal_selection_and_retirement(self):
        self.check_quality_app(['-DFX_H265_APP=1'])

    def check_quality_app(self, flags):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'prores-module'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',*flags,
                '-I',str(ROOT/'include'),*[str(ROOT/p) for p in ['tests/prores_module_fixture.c',
                    'src/video_quality.c','src/platform.c','src/binding_store.c','src/native_call.c','src/accounting.c',
                    'src/services.c','src/module.c','src/sha256.c','src/memory.c','src/extensions.c','src/stream.c']],'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
            subprocess.run([str(binary),'old-core'],check=True)
            subprocess.run([str(binary),'no-menu'],check=True)
            subprocess.run([str(binary),'persistent'],check=True)
            for case in ('retry-cancel','retry-cancel-release','retry-latest','retry-release'):
                with self.subTest(case=case):subprocess.run([str(binary),case],check=True)
    def test_native_owner_fence_and_deferred_stock_restoration(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'video-quality'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
                '-I',str(ROOT/'include'),str(ROOT/'tests/video_quality_fixture.c'),
                str(ROOT/'src/video_quality.c'),str(ROOT/'src/memory.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)

    def test_raw_managed_module_package_capabilities_selection_and_retirement(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'raw-module'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
                '-I',str(ROOT/'include'),*[str(ROOT/p) for p in ['tests/raw_module_fixture.c',
                    'src/video_quality.c','src/platform.c','src/binding_store.c','src/native_call.c','src/accounting.c',
                    'src/services.c','src/module.c','src/sha256.c','src/memory.c','src/extensions.c','src/stream.c']],'-o',str(binary)],check=True)
            for case in ('default','old-core','missing-native','active-fault','retry-cancel','retry-cancel-release','retry-latest','retry-release'):
                with self.subTest(case=case):
                    subprocess.run([str(binary),*(() if case=='default' else (case,))],check=True)
