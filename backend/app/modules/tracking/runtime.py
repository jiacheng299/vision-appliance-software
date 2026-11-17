"""框架侧的轨迹运行时：持有轨迹状态，只调用策略做关联决策。

状态归框架所有，策略只提交 Decision。这样换策略不会改变超时、去重与
排序语义，也不会让一个策略把轨迹表改坏。
"""
from dataclasses import dataclass

from .policy import Decision, Observation, Track, detection_from_box, valid_person

DEFAULT_TIMEOUT_SECONDS = 5.0


@dataclass
class _State:
    id: str
    box: dict
    last_seen: float
    hits: int = 1
    missing_since: float | None = None


class TrackerRuntime:
    def __init__(self, policy, timeout_seconds=DEFAULT_TIMEOUT_SECONDS):
        if timeout_seconds <= 0:
            raise ValueError('timeout_seconds 必须为正数')
        self.policy = policy
        self.timeout = float(timeout_seconds)
        self._states = {}
        self._sequence = 0

    def reset(self):
        self._states.clear()
        self._sequence = 0
        self.policy.reset()

    def _view(self, state):
        # A copy: a policy may inspect and even scribble on the view, but the
        # framework's own copy of the box must not change underneath it.
        return Track(id=state.id, box=dict(state.box), last_seen=state.last_seen,
                     hits=state.hits, missing_since=state.missing_since)

    @property
    def prefix(self):
        return getattr(self.policy, 'track_prefix', self.policy.name)

    def update(self, observation: Observation):
        timestamp = observation.timestamp
        detections = list(observation.detections)
        for state in self._states.values():
            if state.missing_since is None:
                state.missing_since = (state.last_seen if timestamp - state.last_seen > self.timeout
                                       else timestamp)
        live = [state for state in self._states.values()
                if state.missing_since is None or timestamp - state.missing_since <= self.timeout]
        decision = self.policy.decide(observation, tuple(self._view(state) for state in live))
        if not isinstance(decision, Decision):
            raise TypeError('追踪策略必须返回 Decision')
        used = set()
        for track_id, index in decision.associations:
            state = self._states.get(track_id)
            if state is None or not isinstance(index, int) or not 0 <= index < len(detections):
                continue
            if track_id in used:
                continue
            state.box = detections[index].as_box()
            state.last_seen = timestamp
            state.missing_since = None
            state.hits += 1
            used.add(track_id)
        taken = {index for _, index in decision.associations}
        for track_id in decision.lost:
            state = self._states.get(track_id)
            if state is not None and state.missing_since is None:
                state.missing_since = timestamp
        for index in decision.new_detections:
            if not isinstance(index, int) or not 0 <= index < len(detections) or index in taken:
                continue
            self._sequence += 1
            identifier = f'{self.prefix}-{self._sequence}'
            self._states[identifier] = _State(identifier, detections[index].as_box(), timestamp)
        self._states = {identifier: state for identifier, state in self._states.items()
                        if state.missing_since is None
                        or timestamp - state.missing_since <= self.timeout}
        # Only tracks seen in this observation are returned: a missing track keeps
        # its identity for a short gap but contributes no visible target.
        return tuple(sorted((self._view(state) for state in self._states.values()
                             if state.missing_since is None),
                            key=lambda track: track.id))

    @property
    def tracks(self):
        return tuple(sorted((self._view(state) for state in self._states.values()),
                            key=lambda track: track.id))


def observation_from(timestamp, boxes, *, roi=(), frame=None):
    """把执行器手里的检测框转成策略输入；非人员框在入口处就被丢弃。"""
    detections = tuple(detection_from_box(box) for box in (boxes or ()) if valid_person(box))
    return Observation(timestamp=float(timestamp), detections=detections, roi=tuple(roi or ()),
                       frame=dict(frame or {}))
