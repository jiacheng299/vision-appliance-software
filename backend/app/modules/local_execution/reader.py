"""Bounded FFmpeg decoding of controlled local videos and published camera paths."""
from __future__ import annotations

import math
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import urlsplit

from worker.media import LOCAL_INPUT, MediaFailure


class VideoFrameReader:
    """Yield sampled BGR frames; a missing frame is a media failure, never a detection.

    File timestamps are absolute media positions. Camera timestamps use the
    monotonic time when a complete frame was read, preserving gaps in evidence.
    """

    def __init__(self, config, locator: str, kind: str, width: int, height: int,
                 interval: float = 1, start_ms: int = 0, end_ms: int | None = None,
                 stop: threading.Event | None = None):
        if (kind not in ('file', 'camera') or type(width) is not int or type(height) is not int
                or not 0 < width <= 16384 or not 0 < height <= 16384
                or not isinstance(interval, (float, int)) or isinstance(interval, bool)
                or not math.isfinite(interval) or interval <= 0
                or type(start_ms) is not int or start_ms < 0
                or (end_ms is not None and (type(end_ms) is not int or end_ms <= start_ms))
                or (kind == 'camera' and (start_ms != 0 or end_ms is not None))):
            raise MediaFailure('video_decode_failed', '视频采样尺寸、间隔或录像范围无效。')
        timeout = float(config.media_timeout_seconds)
        if not math.isfinite(timeout) or timeout <= 0:
            raise MediaFailure('video_decode_failed', '视频读取等待时间无效。')
        ratio = min(1, 640 / max(width, height))
        self.width, self.height = max(1, round(width * ratio)), max(1, round(height * ratio))
        self.config, self.locator, self.kind = config, locator, kind
        self.interval, self.start_ms, self.end_ms = float(interval), start_ms, end_ms
        self.timeout = min(timeout, 15)
        self.stop = stop if stop is not None else threading.Event()
        self._closed, self._done = threading.Event(), threading.Event()
        self._queue: queue.Queue[tuple[float, bytes]] = queue.Queue(maxsize=2)
        self._process = self._thread = None
        self._failure: MediaFailure | None = None
        self._decoded = 0

    def _input(self) -> str:
        if self.kind == 'file':
            try:
                path = Path(self.locator)
                root = (self.config.var_root / 'media').resolve()
                if not path.is_absolute() or not path.resolve().is_relative_to(root):
                    raise ValueError()
                path = path.resolve(strict=True)
                if not path.is_file():
                    raise ValueError()
                return str(path)
            except (OSError, ValueError, TypeError):
                raise MediaFailure('media_source_forbidden', '只允许读取本机受控媒体目录内的有效视频文件。') from None
        try:
            parts = urlsplit(self.locator)
            path = parts.path.lstrip('/')
            if (parts.scheme != 'rtsp' or parts.hostname != '127.0.0.1'
                    or parts.netloc != f'127.0.0.1:{self.config.media_gateway_rtsp_port}'
                    or parts.username or parts.password or parts.query or parts.fragment
                    or not parts.path.startswith('/') or parts.path.startswith('//')
                    or len(path) > 512 or not re.fullmatch(r'[A-Za-z0-9_./-]+', path)
                    or any(piece in ('', '.', '..') for piece in path.split('/'))):
                raise ValueError()
            return self.locator
        except (ValueError, TypeError, AttributeError):
            raise MediaFailure('camera_address_forbidden', '只允许读取已发布到本机媒体网关的 RTSP 视频。') from None

    def __enter__(self):
        locator = self._input()
        if self._closed.is_set() or self._process is not None:
            raise MediaFailure('video_decode_failed', '视频读取会话不能重复打开。')
        if self.stop.is_set():
            return self
        executable = shutil.which(self.config.ffmpeg)
        if not executable:
            raise MediaFailure('dependency_unavailable', '本地 FFmpeg 不可用，请检查媒体工具配置。')
        arguments = [executable, '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '1']
        if self.kind == 'file':
            arguments.extend(LOCAL_INPUT)
            arguments.extend(['-ss', str(self.start_ms / 1000)])
        else:
            arguments.extend(['-protocol_whitelist', 'tcp,rtsp,rtp', '-format_whitelist', 'rtsp',
                              '-rtsp_transport', 'tcp'])
        arguments.extend(['-i', locator])
        if self.end_ms is not None:
            arguments.extend(['-t', str((self.end_ms - self.start_ms) / 1000)])
        sampler = (f'fps=fps=1/{self.interval}:start_time=0:round=down:eof_action=pass'
                   if self.kind == 'file' else
                   f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{self.interval})'")
        arguments.extend(['-map', '0:v:0', '-an', '-sn', '-dn', '-vf',
                          f'setpts=PTS-STARTPTS,{sampler},scale={self.width}:{self.height}',
                          '-fps_mode', 'passthrough', '-threads', '1', '-pix_fmt', 'bgr24', '-f', 'rawvideo',
                          '-flush_packets', '1', 'pipe:1'])
        try:
            self._process = subprocess.Popen(arguments, shell=False, stdin=subprocess.DEVNULL,
                                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                             bufsize=0, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError:
            raise MediaFailure('dependency_unavailable', '无法启动本地视频解码工具。') from None
        self._thread = threading.Thread(target=self._decode, name='local-video-reader', daemon=True)
        self._thread.start()
        return self

    def _stopping(self) -> bool:
        return self._closed.is_set() or self.stop.is_set()

    def _read_exact(self, size: int) -> bytes:
        result = bytearray()
        while len(result) < size and not self._stopping():
            block = self._process.stdout.read(size - len(result))
            if not block:
                break
            result.extend(block)
        return bytes(result)

    def _put(self, item: tuple[float, bytes]) -> None:
        while not self._stopping():
            try:
                self._queue.put(item, timeout=0 if self.kind == 'camera' else .05)
                return
            except queue.Full:
                if self.kind == 'camera':
                    try:
                        self._queue.get_nowait()
                    except queue.Empty:
                        pass

    def _decode(self) -> None:
        size = self.width * self.height * 3
        try:
            while not self._stopping():
                data = self._read_exact(size)
                if self._stopping():
                    return
                if not data:
                    if self._process.wait(timeout=self.timeout) != 0 or not self._decoded or self.kind == 'camera':
                        self._failure = self._decode_error()
                    return
                if len(data) != size:
                    self._failure = self._decode_error()
                    return
                stamp = (self.start_ms / 1000 + self._decoded * self.interval
                         if self.kind == 'file' else time.monotonic())
                if self.end_ms is not None and stamp >= self.end_ms / 1000:
                    return
                self._decoded += 1
                self._put((stamp, data))
        except (OSError, ValueError, subprocess.SubprocessError):
            if not self._stopping():
                self._failure = self._decode_error()
        finally:
            self._done.set()

    def _decode_error(self) -> MediaFailure:
        if self.kind == 'camera':
            return MediaFailure('camera_frame_timeout', '摄像头未能在限时内提供有效视频帧，请检查媒体网关及推流状态。')
        return MediaFailure('video_decode_failed', '视频解码失败或读取超时，请检查录像文件及所选时间范围。')

    def frames(self):
        if self._process is None and not self._stopping():
            raise MediaFailure('video_decode_failed', '请先打开视频读取会话。')
        deadline = time.monotonic() + self.timeout
        try:
            while not self._stopping():
                try:
                    stamp, data = self._queue.get(timeout=.02)
                except queue.Empty:
                    if self._done.is_set():
                        if self._failure is not None:
                            raise self._failure
                        return
                    if time.monotonic() >= deadline:
                        raise self._decode_error()
                    continue
                if self._stopping():
                    return
                import numpy as np
                frame = np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3).copy()
                yield stamp, frame
                # Time spent by the inference consumer is not decoder waiting time.
                deadline = time.monotonic() + self.timeout
        finally:
            self.close()

    def close(self) -> None:
        self._closed.set()
        if self._process is not None:
            try:
                if self._process.poll() is None:
                    try:
                        self._process.terminate()
                        self._process.wait(timeout=.5)
                    except (OSError, subprocess.TimeoutExpired):
                        self._process.kill()
                        self._process.wait(timeout=1)
            except (OSError, subprocess.SubprocessError):
                pass
            if self._thread is not None and self._thread is not threading.current_thread():
                self._thread.join(timeout=1)
            if self._process.stdout is not None:
                self._process.stdout.close()

    def __exit__(self, *_):
        self.close()
