"""Deterministic person intrusion tracking and zone state.

Only successfully decoded observations advance timers. A short detector gap keeps
the local track identity but contributes no confirmation time. Stream failures
reset the rule to its initial wait-for-clear state.
"""
from dataclasses import dataclass
import math

from .presence import contains


@dataclass
class _Track:
    id: str
    box: dict
    last_seen: float
    missing_since: float | None = None


@dataclass
class _Candidate:
    confirmed_seconds: float
    last_observation: float
    visible_previous: bool = True


@dataclass(frozen=True)
class TrackedTarget:
    id: str
    box: dict


@dataclass(frozen=True)
class IntrusionObservation:
    count: int
    phase: str
    confirmed_seconds: float
    alarm: bool
    track_id: str | None
    targets: tuple[TrackedTarget, ...]


def _center(box):
    return box['x'] + box['width'] / 2, box['y'] + box['height'] / 2


def _iou(left, right):
    lx1, ly1, lx2, ly2 = left['x'], left['y'], left['x'] + left['width'], left['y'] + left['height']
    rx1, ry1, rx2, ry2 = right['x'], right['y'], right['x'] + right['width'], right['y'] + right['height']
    overlap = max(0, min(lx2, rx2) - max(lx1, rx1)) * max(0, min(ly2, ry2) - max(ly1, ry1))
    union = left['width'] * left['height'] + right['width'] * right['height'] - overlap
    return overlap / union if union > 0 else 0


def _valid_person(box):
    if not isinstance(box, dict) or box.get('label') != 'person':
        return False
    values = [box.get(key) for key in ('x', 'y', 'width', 'height')]
    return (all(type(value) in (int, float) and math.isfinite(value) for value in values)
            and values[2] > 0 and values[3] > 0)


class _PersonTracker:
    """Small fixed-camera IoU/centre tracker; it performs no identity recognition."""

    def __init__(self, timeout_seconds):
        self.timeout = timeout_seconds
        self.tracks = {}
        self.sequence = 0

    def reset(self):
        self.tracks.clear()
        self.sequence = 0

    def update(self, timestamp, boxes):
        detections = [dict(box) for box in boxes if _valid_person(box)]
        for track in self.tracks.values():
            if track.missing_since is None:
                track.missing_since = track.last_seen if timestamp - track.last_seen > self.timeout else timestamp
        pairs = []
        for track in self.tracks.values():
            if track.missing_since is not None and timestamp - track.missing_since > self.timeout:
                continue
            tx, ty = _center(track.box)
            for index, box in enumerate(detections):
                bx, by = _center(box)
                distance = math.hypot(tx - bx, ty - by)
                overlap = _iou(track.box, box)
                if overlap >= .05 or distance <= .2:
                    pairs.append((max(overlap, 1 - distance), track.id, index))
        used_tracks, used_detections, output = set(), set(), []
        for _, identifier, index in sorted(pairs, reverse=True):
            if identifier in used_tracks or index in used_detections:
                continue
            track = self.tracks[identifier]
            track.box, track.last_seen, track.missing_since = detections[index], timestamp, None
            used_tracks.add(identifier); used_detections.add(index)
            output.append(TrackedTarget(identifier, track.box))
        for index, box in enumerate(detections):
            if index in used_detections:
                continue
            self.sequence += 1
            identifier = f'person-{self.sequence}'
            self.tracks[identifier] = _Track(identifier, box, timestamp)
            output.append(TrackedTarget(identifier, box))
        self.tracks = {identifier: track for identifier, track in self.tracks.items()
                       if track.missing_since is None or timestamp - track.missing_since <= self.timeout}
        return tuple(sorted(output, key=lambda target: target.id))


class IntrusionRule:
    """One alarm per armed zone-occupancy episode."""

    def __init__(self, regions, entry_seconds=8, occlusion_seconds=5, exit_seconds=10, max_gap_seconds=2):
        values = (entry_seconds, occlusion_seconds, exit_seconds, max_gap_seconds)
        if (not regions or any(len(region) < 3 for region in regions)
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value) or value <= 0 for value in values)
                or occlusion_seconds >= exit_seconds or max_gap_seconds > occlusion_seconds):
            raise ValueError('Invalid intrusion monitoring conditions')
        self.regions = regions
        self.entry_seconds = float(entry_seconds)
        self.occlusion_seconds = float(occlusion_seconds)
        self.exit_seconds = float(exit_seconds)
        self.max_gap_seconds = float(max_gap_seconds)
        self.tracker = _PersonTracker(self.occlusion_seconds)
        self.mark_unavailable()

    def mark_unavailable(self):
        self.tracker.reset()
        self.waiting_clear = True
        self.alarmed = False
        self.clear_since = None
        self.candidates = {}
        self.last_timestamp = None

    def _inside(self, target):
        box = target.box
        foot = box['x'] + box['width'] / 2, box['y'] + box['height']
        return any(contains(region, foot) for region in self.regions)

    def _result(self, count, phase, confirmed=0, alarm=False, track_id=None, targets=()):
        return IntrusionObservation(count, phase, float(confirmed), alarm, track_id, targets)

    def observe(self, timestamp, boxes):
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not math.isfinite(timestamp) or timestamp < 0
                or (self.last_timestamp is not None and timestamp < self.last_timestamp)):
            raise ValueError('Invalid observation time')
        self.last_timestamp = float(timestamp)
        targets = self.tracker.update(float(timestamp), boxes)
        inside = tuple(target for target in targets if self._inside(target))
        inside_ids = {target.id for target in inside}
        current_ids = {target.id for target in targets}
        count = len(inside)

        if self.waiting_clear:
            if count:
                self.clear_since = None
            else:
                self.clear_since = float(timestamp) if self.clear_since is None else self.clear_since
                if timestamp - self.clear_since >= self.exit_seconds:
                    self.waiting_clear = False
                    self.clear_since = None
                    return self._result(count, 'armed', targets=targets)
            return self._result(count, 'waiting_clear', targets=targets)

        if self.alarmed:
            if count:
                self.clear_since = None
            else:
                self.clear_since = float(timestamp) if self.clear_since is None else self.clear_since
                if timestamp - self.clear_since >= self.exit_seconds:
                    self.alarmed = False
                    self.clear_since = None
                    self.candidates.clear()
                    return self._result(count, 'armed', targets=targets)
            return self._result(count, 'alarmed', targets=targets)

        for identifier in list(self.candidates):
            candidate = self.candidates[identifier]
            if identifier in inside_ids:
                if candidate.visible_previous and timestamp - candidate.last_observation <= self.max_gap_seconds:
                    candidate.confirmed_seconds += max(0, timestamp - candidate.last_observation)
                candidate.last_observation = float(timestamp)
                candidate.visible_previous = True
            elif identifier in current_ids or identifier not in self.tracker.tracks:
                del self.candidates[identifier]
            else:
                candidate.visible_previous = False
        for target in inside:
            self.candidates.setdefault(target.id, _Candidate(0, float(timestamp)))

        eligible = [(candidate.confirmed_seconds, identifier) for identifier, candidate in self.candidates.items()
                    if identifier in inside_ids and candidate.confirmed_seconds >= self.entry_seconds]
        if eligible:
            confirmed, identifier = max(eligible)
            self.alarmed = True
            self.clear_since = None
            return self._result(count, 'alarmed', confirmed, True, identifier, targets)
        confirmed = max((candidate.confirmed_seconds for candidate in self.candidates.values()), default=0)
        phase = 'confirming' if inside else 'occluded' if self.candidates else 'armed'
        return self._result(count, phase, confirmed, targets=targets)
