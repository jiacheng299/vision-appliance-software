"""候选会话的影子对照（S14）：同一批帧分别喂给两个会话并比对输出。

与 `preheat.measure` 的区别：那次只测"多开一份会话要多少资源"，这次真的让
两个会话在同一批帧上推理，并逐帧比对检测结果。本机只有一份可信 ONNX，
因此两次加载的是同一份产物——对照结果能证明「影子通道的确定性」，不能证明
「换成另一个模型会更准」。这一点写在返回值的 notes 里，不靠读者猜。
"""
from dataclasses import asdict, dataclass
import time

DEFAULT_FRAMES = 8
IOU_MATCH = 0.5


@dataclass(frozen=True)
class ShadowComparison:
    available: bool
    reason: str | None
    mode: str                    # 'file' | 'synthetic'
    frames: int
    identical_artifact: bool
    exact_frames: int = 0        # 两个会话输出完全一致的帧数
    iou_frames: int = 0          # 允许 IoU≥0.5 匹配后一致的帧数
    mean_iou: float | None = None
    detections_a: int = 0
    detections_b: int = 0
    latency_a_ms: float | None = None
    latency_b_ms: float | None = None
    notes: tuple = ()

    def as_dict(self):
        payload = asdict(self)
        payload['notes'] = list(self.notes)
        return payload

    @property
    def agree(self):
        return self.available and self.iou_frames == self.frames


def _iou(left, right):
    lx1, ly1 = left['x'], left['y']
    lx2, ly2 = lx1 + left['width'], ly1 + left['height']
    rx1, ry1 = right['x'], right['y']
    rx2, ry2 = rx1 + right['width'], ry1 + right['height']
    overlap = max(0, min(lx2, rx2) - max(lx1, rx1)) * max(0, min(ly2, ry2) - max(ly1, ry1))
    union = left['width'] * left['height'] + right['width'] * right['height'] - overlap
    return overlap / union if union > 0 else 0.0


def _match(left, right):
    """Greedy IoU matching; returns (matched pairs, mean IoU)."""
    pairs, used, ious = [], set(), []
    for index, box in enumerate(left):
        best, best_index = 0.0, None
        for other_index, other in enumerate(right):
            if other_index in used:
                continue
            score = _iou(box, other)
            if score > best:
                best, best_index = score, other_index
        if best_index is not None and best >= IOU_MATCH:
            used.add(best_index)
            pairs.append((index, best_index))
            ious.append(best)
    return pairs, (sum(ious) / len(ious) if ious else None)


def _same(left, right, tolerance=1e-6):
    if len(left) != len(right):
        return False
    return all(abs(a[key] - b[key]) <= tolerance
               for a, b in zip(left, right)
               for key in ('x', 'y', 'width', 'height'))


def compare(path_a, path_b, frames, *, detector_factory=None):
    """Run both sessions over the same frames and report how they differ."""
    notes = ['两个会话加载的是同一份 ONNX 时可验证影子通道的确定性，',
             '但不能证明"换模型会更准"——本机只有一种检测能力。']
    frames = list(frames)
    if not frames:
        return ShadowComparison(False, '没有可供对照的帧', 'synthetic', 0, path_a == path_b,
                                notes=tuple(notes))
    if detector_factory is None:
        try:
            from ..models.yolo import YoloPersonDetector as detector_factory
        except ImportError as error:
            return ShadowComparison(False, f'缺少推理依赖：{error}', 'synthetic', len(frames),
                                    path_a == path_b, notes=tuple(notes))
    try:
        shadow = detector_factory(path_b, confidence=0.5)
        current = detector_factory(path_a, confidence=0.5)
    except Exception as error:
        return ShadowComparison(False, f'会话加载失败：{error}', 'synthetic', len(frames),
                                path_a == path_b, notes=tuple(notes))
    exact = iou_matches = 0
    total_a = total_b = 0
    ious = []
    started = time.perf_counter()
    left_all = [current.detect(frame) for frame in frames]
    latency_a = (time.perf_counter() - started) * 1000.0 / len(frames)
    started = time.perf_counter()
    right_all = [shadow.detect(frame) for frame in frames]
    latency_b = (time.perf_counter() - started) * 1000.0 / len(frames)
    for left, right in zip(left_all, right_all):
        total_a += len(left)
        total_b += len(right)
        if _same(left, right):
            exact += 1
        pairs, mean = _match(left, right)
        if len(pairs) == max(len(left), len(right)):
            iou_matches += 1
        if mean is not None:
            ious.append(mean)
    if exact == len(frames):
        notes.append('逐帧输出完全一致：同一产物的影子通道是确定性的。')
    return ShadowComparison(
        available=True, reason=None, mode='synthetic', frames=len(frames),
        identical_artifact=path_a == path_b, exact_frames=exact, iou_frames=iou_matches,
        mean_iou=(sum(ious) / len(ious)) if ious else None,
        detections_a=total_a, detections_b=total_b,
        latency_a_ms=round(latency_a, 2), latency_b_ms=round(latency_b, 2),
        notes=tuple(notes))


def frames_from_video(path, *, count=DEFAULT_FRAMES):
    """Sample evenly spaced frames from a local recording; None when unreadable."""
    try:
        import cv2
    except ImportError:
        return None
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return None
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return None
        collected = []
        for index in range(max(1, count)):
            position = int(total * (index + 0.5) / max(1, count))
            capture.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, frame = capture.read()
            if ok and frame is not None:
                collected.append(frame)
        return collected or None
    finally:
        capture.release()


def synthetic_frames(count=DEFAULT_FRAMES, size=(480, 640)):
    """Deterministic frames for a smoke test when no recording is available."""
    import numpy as np
    rng = np.random.default_rng(20261117)
    return [rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
            for _ in range(max(1, count))]
