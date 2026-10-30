"""The returned JPEG must contain its own frame and matching detection boxes."""
import cv2
import numpy as np
import asyncio

from app.modules.local_execution.preview import DetectionFrames
from app.modules.agents.schemas import Region


def test_continuous_stream_sends_new_complete_frames_and_stops_on_missing_data():
    from app.shared.detection_stream import multipart_frames
    frames=iter([(b'one','time-1'),(b'one','time-1'),(b'two','time-2'),None])
    async def read(): return next(frames)
    async def disconnected(): return False
    async def collect(): return [part async for part in multipart_frames(read,disconnected)]
    parts=asyncio.run(collect())
    assert len(parts)==2
    assert b'Content-Type: image/jpeg\r\n' in parts[0]
    assert b'Content-Length: 3\r\n' in parts[0]
    assert parts[0].endswith(b'\r\n\r\none\r\n')
    assert parts[1].endswith(b'\r\n\r\ntwo\r\n')


def test_continuous_stream_stops_reading_when_browser_disconnects():
    from app.shared.detection_stream import multipart_frames
    async def read(): raise AssertionError('Disconnected clients must not keep polling')
    async def disconnected(): return True
    async def collect(): return [part async for part in multipart_frames(read,disconnected)]
    assert asyncio.run(collect())==[]


def test_preview_keeps_matching_frame_and_boxes_isolated_per_run():
    frames = DetectionFrames()
    region = Region(id='roi', points=[(0, 0), (1, 0), (1, 1), (0, 1)])
    frame = np.zeros((120, 200, 3), dtype=np.uint8)
    frame[50:70, 80:100] = (255, 0, 0)
    box = dict(x=.2, y=.2, width=.3, height=.6)
    frames.publish('one', frame, [box], [region])
    first = frames.read('one')
    frames.publish('two', np.full_like(frame, 255), [], [region])
    assert frames.read('one') == first
    image = cv2.imdecode(np.frombuffer(first[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    # Actual input content and corresponding green border share a single JPEG.
    assert image[60, 90, 0] > 200 and image[60, 90, 1] < 40
    assert image[50, 40, 1] > 120 and image[50, 40, 2] < 90
    other = cv2.imdecode(np.frombuffer(frames.read('two')[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert other[60, 90].min() > 240
    assert frames.read('missing') is None


def test_preview_expires_and_can_be_discarded_without_serving_old_boxes(monkeypatch):
    clock = [10.]
    monkeypatch.setattr('app.modules.local_execution.preview.time.monotonic', lambda: clock[0])
    frames = DetectionFrames()
    frame = np.zeros((30, 30, 3), dtype=np.uint8)
    frames.publish('one', frame, [], [])
    assert frames.read('one') is not None
    clock[0] = 13.1
    assert frames.read('one') is None
    frames.publish('one', frame, [], [])
    frames.discard('one')
    assert frames.read('one') is None
