"""Reader evidence uses real FFmpeg and controlled pipe failures, never fake detections."""
import importlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from worker.media import LOCAL_INPUT, MediaFailure


def test_reader_is_available_for_the_local_runtime():
    assert importlib.util.find_spec('app.modules.local_execution.reader') is not None


@pytest.fixture
def reader_module():
    name = 'app.modules.local_execution.reader'
    assert importlib.util.find_spec(name) is not None, 'VideoFrameReader implementation is missing'
    return importlib.import_module(name)


@pytest.fixture
def config(tmp_path):
    media = tmp_path / 'media'
    media.mkdir()
    return SimpleNamespace(var_root=tmp_path, ffmpeg='ffmpeg', media_timeout_seconds=.08,
                           media_gateway_rtsp_port=8554)


@pytest.fixture
def local_file(config):
    path = config.var_root / 'media' / 'controlled.mp4'
    path.write_bytes(b'controlled fixture')
    return str(path)


@pytest.fixture
def video(config):
    pytest.importorskip('numpy')
    bundled = Path(__file__).resolve().parents[2] / 'var/tools/ffmpeg/bin/ffmpeg.exe'
    executable = shutil.which(os.environ.get('VISION_FFMPEG', 'ffmpeg'))
    if not executable and bundled.is_file():
        executable = str(bundled)
    if not executable:
        pytest.skip('Real local FFmpeg is required')
    config.ffmpeg = executable
    config.media_timeout_seconds = 5
    target = config.var_root / 'media' / 'red.mp4'
    result = subprocess.run([executable, '-nostdin', '-hide_banner', '-loglevel', 'error',
                             '-f', 'lavfi', '-i', 'color=c=red:s=960x540:r=10:d=4',
                             '-c:v', 'mpeg4', '-pix_fmt', 'yuv420p', '-y', str(target)],
                            shell=False, capture_output=True, timeout=15,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, 'Local FFmpeg could not synthesize the test video'
    return str(target)


class Pipe(io.BytesIO):
    def __init__(self, data=b'', blocked=False):
        super().__init__(data)
        self.blocked = blocked
        self.release = threading.Event()
        self.exhausted = threading.Event()

    def read(self, size=-1):
        if self.blocked:
            self.release.wait(5)
            return b''
        result = super().read(min(size, 7))
        if not result:
            self.exhausted.set()
        return result


class Process:
    def __init__(self, data=b'', blocked=False, stubborn=False, returncode=0):
        self.stdout = Pipe(data, blocked)
        self.returncode = None if blocked else returncode
        self.stubborn = stubborn
        self.terminated = self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is None:
            if not self.stdout.release.wait(timeout):
                raise subprocess.TimeoutExpired('private-command', timeout)
        return self.returncode

    def terminate(self):
        self.terminated = True
        if not self.stubborn:
            self.returncode = -15
            self.stdout.release.set()

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.stdout.release.set()


def launch(monkeypatch, reader_module, process):
    calls = []

    def popen(arguments, **options):
        calls.append((arguments, options))
        return process

    monkeypatch.setattr(reader_module.subprocess, 'Popen', popen)
    monkeypatch.setattr(reader_module.shutil, 'which', lambda _: 'controlled-ffmpeg')
    return calls


def test_real_ffmpeg_samples_selected_range_in_absolute_media_seconds(reader_module, config, video):
    np = pytest.importorskip('numpy')
    with reader_module.VideoFrameReader(config, video, 'file', 960, 540,
                                       interval=.5, start_ms=1250, end_ms=3250) as reader:
        frames = list(reader.frames())
    assert [timestamp for timestamp, _ in frames] == pytest.approx([1.25, 1.75, 2.25, 2.75])
    for _, frame in frames:
        assert frame.shape == (360, 640, 3)
        assert frame.dtype == np.uint8
        assert frame[0, 0, 2] > 200 and frame[0, 0, 0] < 10


def test_a_valid_selected_range_shorter_than_the_interval_still_yields_its_first_frame(
        reader_module, config, video):
    with reader_module.VideoFrameReader(config, video, 'file', 960, 540,
                                       interval=1, start_ms=3750, end_ms=3950) as reader:
        frames = list(reader.frames())
    assert [timestamp for timestamp, _ in frames] == [3.75]


@pytest.mark.parametrize('locator', ['https://example.invalid/secret.mp4', 'relative.mp4', 'pipe:0'])
def test_file_reader_refuses_urls_and_relative_paths(reader_module, config, locator):
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, locator, 'file', 320, 180):
            pass
    assert caught.value.code == 'media_source_forbidden'
    assert locator not in str(caught.value)


def test_file_reader_refuses_absolute_files_outside_controlled_media(reader_module, config):
    outside = config.var_root / 'private-secret.mp4'
    outside.write_bytes(b'private')
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, str(outside), 'file', 320, 180):
            pass
    assert caught.value.code == 'media_source_forbidden'
    assert 'private-secret' not in str(caught.value)


@pytest.mark.parametrize('locator', [
    'rtsp://example.invalid:8554/video', 'rtsp://localhost:8554/video',
    'rtsp://127.0.0.1:9554/video', 'rtsp://user:password@127.0.0.1:8554/video',
    'rtsp://127.0.0.1:8554/../video', 'rtsp://127.0.0.1:8554/video?secret=1',
    'http://127.0.0.1:8554/video', 'rtsp://127.0.0.1:8554/video#fragment',
])
def test_camera_reader_only_accepts_the_local_published_gateway(reader_module, config, locator):
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, locator, 'camera', 320, 180):
            pass
    assert caught.value.code == 'camera_address_forbidden'
    assert 'password' not in str(caught.value)


@pytest.mark.parametrize('kind', ['file', 'camera'])
def test_process_uses_restricted_protocols_without_a_shell_or_diagnostic_output(
        reader_module, config, local_file, monkeypatch, kind):
    process = Process(blocked=True)
    calls = launch(monkeypatch, reader_module, process)
    locator = local_file if kind == 'file' else 'rtsp://127.0.0.1:8554/camera-one'
    with reader_module.VideoFrameReader(config, locator, kind, 320, 180):
        pass
    arguments, options = calls[0]
    assert options['shell'] is False
    assert options['stderr'] == subprocess.DEVNULL
    assert options['stdin'] == subprocess.DEVNULL
    if kind == 'file':
        for option in LOCAL_INPUT:
            assert option in arguments
    else:
        assert arguments[arguments.index('-protocol_whitelist') + 1] == 'tcp,rtsp,rtp'
        assert arguments[arguments.index('-rtsp_transport') + 1] == 'tcp'
    assert process.terminated


@pytest.mark.parametrize('kind,code', [('file', 'video_decode_failed'), ('camera', 'camera_frame_timeout')])
def test_a_stalled_decoder_times_out_and_releases_the_process(
        reader_module, config, local_file, monkeypatch, kind, code):
    process = Process(blocked=True)
    launch(monkeypatch, reader_module, process)
    locator = local_file if kind == 'file' else 'rtsp://127.0.0.1:8554/camera-one'
    started = time.monotonic()
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, locator, kind, 320, 180) as reader:
            next(reader.frames())
    assert caught.value.code == code
    assert time.monotonic() - started < 1
    assert process.terminated


def test_external_stop_interrupts_a_blocked_read_without_reporting_absence(
        reader_module, config, local_file, monkeypatch):
    process = Process(blocked=True)
    launch(monkeypatch, reader_module, process)
    config.media_timeout_seconds = 10
    stop = threading.Event()
    timer = threading.Timer(.05, stop.set)
    timer.start()
    try:
        started = time.monotonic()
        with reader_module.VideoFrameReader(config, local_file, 'file', 320, 180, stop=stop) as reader:
            assert list(reader.frames()) == []
        assert time.monotonic() - started < 1
        assert process.terminated
    finally:
        timer.cancel()


def test_context_exit_kills_a_process_that_ignores_termination(
        reader_module, config, local_file, monkeypatch):
    process = Process(blocked=True, stubborn=True)
    launch(monkeypatch, reader_module, process)
    started = time.monotonic()
    with reader_module.VideoFrameReader(config, local_file, 'file', 320, 180):
        pass
    assert process.terminated and process.killed
    assert time.monotonic() - started < 2


def test_context_exit_still_kills_if_terminate_reports_an_os_error(
        reader_module, config, local_file, monkeypatch):
    class FailingTerminate(Process):
        def terminate(self):
            self.terminated = True
            raise OSError('private process diagnostic')

    process = FailingTerminate(blocked=True)
    launch(monkeypatch, reader_module, process)
    try:
        with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2):
            pass
        assert process.killed
    finally:
        process.kill()


def test_chunked_reads_keep_every_file_sample_without_upscaling(
        reader_module, config, local_file, monkeypatch):
    pytest.importorskip('numpy')
    process = Process(b''.join(bytes([value]) * 24 for value in range(6)))
    launch(monkeypatch, reader_module, process)
    with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2, interval=.5) as reader:
        assert not process.stdout.exhausted.wait(.15), 'File decoder must apply bounded backpressure'
        frames = list(reader.frames())
    assert [stamp for stamp, _ in frames] == [0, .5, 1, 1.5, 2, 2.5]
    assert [int(frame[0, 0, 0]) for _, frame in frames] == list(range(6))
    assert all(frame.shape == (2, 4, 3) for _, frame in frames)


@pytest.mark.parametrize('payload,returncode', [(b'', 1), (b'partial', 0)])
def test_failed_or_partial_frames_are_errors_instead_of_empty_observations(
        reader_module, config, local_file, monkeypatch, payload, returncode):
    launch(monkeypatch, reader_module, Process(payload, returncode=returncode))
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2) as reader:
            list(reader.frames())
    assert caught.value.code == 'video_decode_failed'


def test_corrupt_file_fails_with_real_ffmpeg_without_exposing_its_path(reader_module, config, video):
    Path(video).write_bytes(b'invalid media secret')
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, video, 'file', 960, 540) as reader:
            list(reader.frames())
    assert caught.value.code == 'video_decode_failed'
    assert video not in str(caught.value)


def test_camera_discards_older_queued_frames_and_uses_monotonic_observation_times(
        reader_module, config, monkeypatch):
    pytest.importorskip('numpy')
    process = Process(b''.join(bytes([value]) * 24 for value in range(10)))
    launch(monkeypatch, reader_module, process)
    before = time.monotonic()
    with reader_module.VideoFrameReader(config, 'rtsp://127.0.0.1:8554/published/path',
                                       'camera', 4, 2) as reader:
        assert process.stdout.exhausted.wait(1.5)
        frames = reader.frames()
        sampled = [next(frames), next(frames)]
        with pytest.raises(MediaFailure) as caught:
            next(frames)
    assert caught.value.code == 'camera_frame_timeout'
    assert [int(frame[0, 0, 0]) for _, frame in sampled] == [8, 9]
    assert before <= sampled[0][0] <= sampled[1][0] <= time.monotonic()


def test_a_missing_decoder_is_reported_without_starting_a_process(
        reader_module, config, local_file, monkeypatch):
    monkeypatch.setattr(reader_module.shutil, 'which', lambda _: None)
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2):
            pass
    assert caught.value.code == 'dependency_unavailable'


def test_process_start_failure_does_not_leak_private_os_error(
        reader_module, config, local_file, monkeypatch):
    launch(monkeypatch, reader_module, Process())

    def failed(*_, **__):
        raise OSError('private-media-path-and-password')

    monkeypatch.setattr(reader_module.subprocess, 'Popen', failed)
    with pytest.raises(MediaFailure) as caught:
        with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2):
            pass
    assert caught.value.code == 'dependency_unavailable'
    assert 'private' not in str(caught.value)


def test_reader_thread_is_released_when_a_file_queue_is_full(
        reader_module, config, local_file, monkeypatch):
    previous = {thread.ident for thread in threading.enumerate()}
    launch(monkeypatch, reader_module, Process(b'\0' * (24 * 8)))
    with reader_module.VideoFrameReader(config, local_file, 'file', 4, 2):
        time.sleep(.08)
    assert not [thread for thread in threading.enumerate()
                if thread.name == 'local-video-reader' and thread.ident not in previous]


def test_camera_sampler_never_synthesizes_frames_to_fill_a_timestamp_gap(
        reader_module, config, video, monkeypatch):
    gap_video = config.var_root / 'media' / 'gap.mp4'
    result = subprocess.run([config.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                             '-f', 'lavfi', '-i', 'color=c=red:s=16x16:r=1:d=3',
                             '-vf', 'setpts=N*4/TB', '-fps_mode', 'vfr', '-c:v', 'mpeg4',
                             '-y', str(gap_video)], shell=False, capture_output=True, timeout=10,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0
    with monkeypatch.context() as patched:
        calls = launch(patched, reader_module, Process(blocked=True))
        with reader_module.VideoFrameReader(config, 'rtsp://127.0.0.1:8554/camera',
                                           'camera', 16, 16):
            pass
    arguments = calls[0][0]
    sampler = arguments[arguments.index('-vf') + 1]
    mode = arguments[arguments.index('-fps_mode') + 1] if '-fps_mode' in arguments else 'auto'
    decoded = subprocess.run([config.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error',
                              *LOCAL_INPUT, '-i', str(gap_video), '-vf', sampler,
                              '-fps_mode', mode, '-pix_fmt', 'bgr24', '-f', 'rawvideo', 'pipe:1'],
                             shell=False, capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert decoded.returncode == 0
    assert len(decoded.stdout) // (16 * 16 * 3) == 3, 'Only the three actual decoded observations are evidence'
