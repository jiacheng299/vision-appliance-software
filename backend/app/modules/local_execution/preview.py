"""Bounded, ephemeral previews: pixels and boxes are encoded from the same frame."""
from threading import RLock
import time

from ...shared.models import now


class DetectionFrames:
    def __init__(self):
        self.lock = RLock()
        self.frames = {}

    def publish(self, run_id, frame, boxes, regions, *, alert_active=False):
        import cv2
        import numpy as np
        image = frame.copy()
        height, width = image.shape[:2]
        for region in regions:
            points = np.array([(round(x*(width-1)), round(y*(height-1)))
                               for x, y in region.points], dtype=np.int32)
            cv2.polylines(image, [points], True, (0, 0, 255) if alert_active else (0, 180, 255), 2)
        for box in boxes:
            x, y, w, h = (box[key] for key in ('x', 'y', 'width', 'height'))
            cv2.rectangle(image, (round(x*width), round(y*height)),
                          (round((x+w)*width), round((y+h)*height)), (0, 0, 255) if alert_active else (0, 200, 0), 2)
        ok, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            raise ValueError('Detection preview encoding failed')
        with self.lock:
            self.frames[run_id] = (time.monotonic(), encoded.tobytes(), now())

    def read(self, run_id):
        with self.lock:
            entry = self.frames.get(run_id)
            if not entry or time.monotonic() - entry[0] > 3:
                self.frames.pop(run_id, None)
                return None
            return entry[1:]

    def discard(self, run_id):
        with self.lock:
            self.frames.pop(run_id, None)
