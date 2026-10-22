import unittest,tempfile,hashlib,io
from pathlib import Path
from deploy.scripts.simulated_cameras import publisher_command, media_config, register_sources, verified_download
from unittest.mock import Mock, patch

class CameraLabTests(unittest.TestCase):
 def test_recording_loops_in_realtime_and_uses_tcp(self):
  cmd=publisher_command('ffmpeg',{'path':'plaza','file':'plaza.mp4'},Path('samples'))
  self.assertIn('-re',cmd);self.assertEqual(cmd[cmd.index('-stream_loop')+1],'-1')
  self.assertEqual(cmd[-1],'rtsp://127.0.0.1:8554/plaza');self.assertEqual(cmd[cmd.index('-rtsp_transport')+1],'tcp')
 def test_live_camera_is_not_a_looping_recording(self):
  cmd=publisher_command('ffmpeg',{'path':'pendulum','url':'https://kip.uni-heidelberg.de/mjpg/video.mjpg'},Path('samples'))
  self.assertNotIn('-stream_loop',cmd);self.assertNotIn('-re',cmd)
  self.assertIn('-use_wallclock_as_timestamps',cmd)
  self.assertIn('https://kip.uni-heidelberg.de/mjpg/video.mjpg',cmd)
 def test_services_only_bind_loopback_and_known_paths(self):
  config=media_config([{'path':'plaza'},{'path':'night'},{'path':'pendulum'}])
  for port in (8554,8888,9997):self.assertIn('127.0.0.1:'+str(port),config)
  self.assertIn('rtspTransports: [tcp]',config);self.assertIn('webrtc: no',config)
  self.assertIn('moq: no',config)
  self.assertNotIn('all_others',config)
 def test_registration_uses_existing_camera_without_duplicate(self):
  request=Mock();request.side_effect=[{'items':[{'id':'existing','address':'rtsp://127.0.0.1:8554/plaza'}],'next_cursor':None}]
  rows=register_sources([{'path':'plaza','name':'Loop sample'}],request)
  self.assertEqual(rows[0]['id'],'existing');self.assertEqual(request.call_count,1)
 def test_bad_download_never_replaces_cached_file(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'sample.mp4';target.write_bytes(b'old')
   spec={'url':'https://example.test/sample.mp4','bytes':3,'sha256':hashlib.sha256(b'new').hexdigest()}
   with patch('deploy.scripts.simulated_cameras.HTTP.open',return_value=io.BytesIO(b'bad')):
    with self.assertRaisesRegex(ValueError,'checksum'):verified_download(spec,target)
   self.assertEqual(target.read_bytes(),b'old');self.assertFalse(target.with_suffix('.mp4.part').exists())
 def test_verified_cache_needs_no_network(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'sample.mp4';target.write_bytes(b'new')
   spec={'url':'https://example.test/sample.mp4','bytes':3,'sha256':hashlib.sha256(b'new').hexdigest()}
   with patch('deploy.scripts.simulated_cameras.HTTP.open') as network:
    self.assertEqual(verified_download(spec,target),target);network.assert_not_called()
 def test_invalid_path_is_rejected(self):
  with self.assertRaises(ValueError):media_config([{'path':'../other'}])

if __name__=='__main__':unittest.main()
