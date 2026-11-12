from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]


class RecordingTests(unittest.TestCase):
    def test_immutable_choice_and_positive_retirement(self):
        cc=shutil.which('clang') or shutil.which('cc')
        if not cc:self.skipTest('C compiler required')
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'recording'
            subprocess.run([cc,'-std=c11','-Wall','-Wextra','-Werror','-I',str(ROOT/'include'),
                *[str(ROOT/p) for p in ('tests/video_recording_fixture.c','src/video_recording.c','src/memory.c')],
                '-o',str(output)],check=True)
            subprocess.run([str(output)],check=True)
