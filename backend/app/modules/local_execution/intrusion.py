"""Deterministic person intrusion tracking and zone state.

Only successfully decoded observations advance timers. A short detector gap keeps
the local track identity but contributes no confirmation time. Stream failures
reset the rule to its initial wait-for-clear state.

关联本身交给可替换的追踪策略（见 modules/tracking）：这里只定义规则状态机，
不实现具体的匹配算法。
"""
from dataclasses import dataclass
import math

from .presence import contains
from ..tracking import registry as tracker_registry
from ..tracking.runtime import TrackerRuntime, observation_from


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


class _PersonTracker:
    """Adapter: the rule keeps its own vocabulary while the policy does the pairing."""

    def __init__(self, timeout_seconds, policy_name='heuristic-iou'):
        self.runtime = TrackerRuntime(tracker_registry.create(policy_name),
                                      timeout_seconds=timeout_seconds)

    def reset(self):
        self.runtime.reset()

    @property
    def track_ids(self):
        return {track.id for track in self.runtime.tracks}

    def update(self, timestamp, boxes):
        tracks = self.runtime.update(observation_from(timestamp, boxes))
        return tuple(sorted((TrackedTarget(track.id, track.box) for track in tracks),
                            key=lambda target: target.id))



class IntrusionRule:
    """One alarm per armed zone-occupancy episode."""

    def __init__(self, regions, entry_seconds=8, occlusion_seconds=5, exit_seconds=10, max_gap_seconds=2,
                 policy_name='heuristic-iou'):
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
        self.tracker = _PersonTracker(self.occlusion_seconds, policy_name)
        self.mark_unavailable()

    def mark_unavailable(self):
        self.tracker.reset()
        self.waiting_clear = True
        self.alarmed = False
        self.clear_since = None
        self.candidates = {}
        self.last_timestamp = None

    def contains_target(self, target):
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
        inside = tuple(target for target in targets if self.contains_target(target))
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
            elif identifier in current_ids or identifier not in self.tracker.track_ids:
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
