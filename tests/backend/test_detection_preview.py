"""The returned JPEG must contain its own frame and matching detection boxes."""
import cv2
import numpy as np

from app.modules.local_execution.preview import DetectionFrames
from app.modules.agents.schemas import Region


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
