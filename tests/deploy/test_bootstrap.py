import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from deploy.scripts.bootstrap import dependency_commands, install_component_archive

class ComponentArchiveTests(unittest.TestCase):
    def test_application_setup_installs_locked_vision_runtime(self):
        commands=dependency_commands(Path('python.exe'),'npm.cmd',Path('.'))
        requirements=[command for command,_ in commands if '-r' in command]
        self.assertIn([Path('python.exe'),'-m','pip','install','-r','backend/requirements.txt'],requirements)
        self.assertIn([Path('python.exe'),'-m','pip','install','-r','backend/requirements-vision.txt'],requirements)
        self.assertLess(commands.index((requirements[1],Path('.'))),
                        next(i for i,(command,_) in enumerate(commands) if command[-2:]==['pip','check']))

    def test_verified_archive_only_installs_expected_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'ffmpeg.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('ffmpeg-build/bin/ffmpeg.exe',b'ffmpeg-binary')
                z.writestr('ffmpeg-build/bin/ffprobe.exe',b'ffprobe-binary')
                z.writestr('ffmpeg-build/LICENSE',b'license text')
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            install_component_archive(archive,root/'tools',digest)
            self.assertEqual((root/'tools/bin/ffprobe.exe').read_bytes(),b'ffprobe-binary')
            self.assertTrue((root/'tools/manifest.json').is_file())
    def test_checksum_mismatch_installs_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'bad.zip';archive.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):
                install_component_archive(archive,root/'tools','0'*64)
            self.assertFalse((root/'tools/bin/ffmpeg.exe').exists())
    def test_path_traversal_is_not_extracted(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); archive=root/'ffmpeg.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('../escape.exe',b'bad')
                z.writestr('bin/ffmpeg.exe',b'a');z.writestr('bin/ffprobe.exe',b'b')
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                install_component_archive(archive,root/'tools',digest)
            self.assertFalse((root/'escape.exe').exists())

if __name__=='__main__':unittest.main()
