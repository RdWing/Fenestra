from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class VideoQualityTests(unittest.TestCase):
    def test_prores_app_ui_selection_retry_and_missing_service(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'prores-module'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
                '-I',str(ROOT/'include'),str(ROOT/'tests/prores_module_fixture.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
    def test_native_owner_fence_and_deferred_stock_restoration(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            binary=Path(tmp)/'video-quality'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-Wshadow',
                '-I',str(ROOT/'include'),str(ROOT/'tests/video_quality_fixture.c'),
                str(ROOT/'src/video_quality.c'),str(ROOT/'src/memory.c'),'-o',str(binary)],check=True)
            subprocess.run([str(binary)],check=True)
