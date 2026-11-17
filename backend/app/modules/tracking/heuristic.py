"""固定机位启发式关联策略：IoU 与中心距，不做身份识别。

这是当前唯一真实可用的策略，也是后续学习型策略（如多智能体强化学习）的
参照基线：同样的观测、同样的动作空间，便于对照。
"""
import math

from .policy import Decision

IOU_FLOOR = 0.05
DISTANCE_CEILING = 0.2


def centre(box):
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def iou(left, right):
    lx1, ly1, lx2, ly2 = left['x'], left['y'], left['x'] + left['width'], left['y'] + left['height']
    rx1, ry1, rx2, ry2 = right['x'], right['y'], right['x'] + right['width'], right['y'] + right['height']
    overlap = max(0, min(lx2, rx2) - max(lx1, rx1)) * max(0, min(ly2, ry2) - max(ly1, ry1))
    union = left['width'] * left['height'] + right['width'] * right['height'] - overlap
    return overlap / union if union > 0 else 0


class HeuristicIoUTracker:
    """Greedy IoU/centre association; deterministic and identity-free."""
    name = 'heuristic-iou'
    track_prefix = 'person'
    label = '固定机位 IoU/中心距关联'

    def __init__(self):
        self.last_note = ''

    def reset(self):
        self.last_note = ''

    def decide(self, observation, tracks):
        if not tracks:
            return Decision(new_detections=tuple(range(len(observation.detections))),
                            note='没有既有轨迹')
        if not observation.detections:
            return Decision(lost=tuple(track.id for track in tracks), note='本帧没有检测')
        pairs = []
        for track in tracks:
            tx, ty = centre(track.box)
            for index, detection in enumerate(observation.detections):
                box = detection.as_box()
                bx, by = centre(box)
                distance = math.hypot(tx - bx, ty - by)
                overlap = iou(track.box, box)
                if overlap >= IOU_FLOOR or distance <= DISTANCE_CEILING:
                    pairs.append((max(overlap, 1 - distance), track.id, index))
        associations, used_tracks, used_detections = [], set(), set()
        for _, track_id, index in sorted(pairs, reverse=True):
            if track_id in used_tracks or index in used_detections:
                continue
            associations.append((track_id, index))
            used_tracks.add(track_id)
            used_detections.add(index)
        births = tuple(index for index in range(len(observation.detections))
                       if index not in used_detections)
        lost = tuple(track.id for track in tracks if track.id not in used_tracks)
        self.last_note = f'关联 {len(associations)}，新增 {len(births)}，丢失 {len(lost)}'
        return Decision(associations=tuple(associations), new_detections=births, lost=lost,
                        note=self.last_note)

    def describe(self):
        return {'name': self.name, 'label': self.label, 'kind': 'heuristic',
                'iou_floor': IOU_FLOOR, 'distance_ceiling': DISTANCE_CEILING,
                'identity_aware': False}
