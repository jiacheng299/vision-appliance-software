"""CPU YOLO11 person inference, with optional dependencies imported on use."""
from __future__ import annotations

from pathlib import Path
import math


class YoloPersonDetector:
    def __init__(self, path: Path, confidence: float = 0.5):
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(path)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError('confidence must be a finite number between 0 and 1')
        try:
            import numpy as np
            import cv2
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError('Install backend/requirements-vision.txt to use YOLO inference') from exc
        self._np = np
        self._cv2 = cv2
        self._confidence = float(confidence)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        try:
            self._session = ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])
        except Exception as exc:
            raise ValueError('Invalid or unsupported ONNX model') from exc
        inputs, outputs = self._session.get_inputs(), self._session.get_outputs()
        if len(inputs) != 1 or inputs[0].type != 'tensor(float)':
            raise ValueError('YOLO input must be one float32 NCHW tensor')
        shape = inputs[0].shape
        if (len(shape) != 4 or shape[:2] != [1, 3]
                or any(type(size) is not int or not 32 <= size <= 2048 or size % 32 for size in shape[2:])):
            raise ValueError('YOLO input requires static [1, 3, height, width] dimensions, multiples of 32 from 32 to 2048')
        if (len(outputs) != 1 or outputs[0].type != 'tensor(float)' or len(outputs[0].shape) != 3
                or outputs[0].shape[:2] != [1, 84] or type(outputs[0].shape[2]) is not int
                or not 1 <= outputs[0].shape[2] <= 100000):
            raise ValueError('YOLO output must be raw COCO predictions [1, 84, anchors]')
        self._input_name = inputs[0].name
        self._input_height, self._input_width = shape[2:]
        self._output_shape = tuple(outputs[0].shape)

    def detect(self, frame) -> list[dict]:
        """Detect people in a uint8 BGR frame; boxes use original-image fractions."""
        np, cv2 = self._np, self._cv2
        if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8 or frame.ndim != 3
                or frame.shape[2] != 3 or frame.shape[0] < 1 or frame.shape[1] < 1):
            raise ValueError('frame must be a nonempty uint8 BGR image with three channels')
        height, width = frame.shape[:2]
        ratio = min(self._input_width / width, self._input_height / height)
        resized_width, resized_height = max(1, round(width * ratio)), max(1, round(height * ratio))
        left = (self._input_width - resized_width) // 2
        top = (self._input_height - resized_height) // 2
        resized = cv2.resize(frame, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
        padded = np.full((self._input_height, self._input_width, 3), 114, dtype=np.uint8)
        padded[top:top + resized_height, left:left + resized_width] = resized
        tensor = np.ascontiguousarray(padded[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0
        predictions = self._session.run(None, {self._input_name: tensor})[0]
        if predictions.shape != self._output_shape or not np.isfinite(predictions).all():
            raise ValueError('Invalid YOLO output shape or nonfinite predictions')
        rows = predictions[0].T
        scores = rows[:, 4:]
        if np.any(scores < 0) or np.any(scores > 1):
            raise ValueError('Invalid YOLO output confidence range')
        mask = ((scores.argmax(axis=1) == 0) & (scores[:, 0] >= self._confidence)
                & (rows[:, 2] > 0) & (rows[:, 3] > 0))
        rows = rows[mask]
        if not len(rows):
            return []
        # Undo the integer border. NMS uses full boxes before clipping, preserving IoU.
        boxes = np.empty((len(rows), 4), dtype=np.float32)
        boxes[:, 0] = (rows[:, 0] - rows[:, 2] / 2 - left) / ratio
        boxes[:, 1] = (rows[:, 1] - rows[:, 3] / 2 - top) / ratio
        boxes[:, 2] = (rows[:, 0] + rows[:, 2] / 2 - left) / ratio
        boxes[:, 3] = (rows[:, 1] + rows[:, 3] / 2 - top) / ratio
        confidences = rows[:, 4]
        areas = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
        order = np.argsort(-confidences, kind='stable')
        kept = []
        while order.size:
            current = int(order[0])
            kept.append(current)
            remaining = order[1:]
            if not remaining.size:
                break
            intersection = np.maximum(0, np.minimum(boxes[current, 2:], boxes[remaining, 2:])
                                      - np.maximum(boxes[current, :2], boxes[remaining, :2])).prod(axis=1)
            iou = intersection / (areas[current] + areas[remaining] - intersection)
            order = remaining[iou <= .45]
        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, width)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, height)
        return [dict(label='person', x=float(boxes[i, 0] / width), y=float(boxes[i, 1] / height),
                     width=float((boxes[i, 2] - boxes[i, 0]) / width),
                     height=float((boxes[i, 3] - boxes[i, 1]) / height), confidence=float(confidences[i]))
                for i in kept if boxes[i, 2] > boxes[i, 0] and boxes[i, 3] > boxes[i, 1]]
