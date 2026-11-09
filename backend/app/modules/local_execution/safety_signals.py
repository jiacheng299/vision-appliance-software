"""Diagnostic signals from the local executor's business samples."""
from collections import deque
from dataclasses import dataclass
from itertools import pairwise
import math


@dataclass(frozen=True)
class SafetySignal:
    reason: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class ObservationWindow:
    def __init__(self, max_gap_seconds: float):
        self.max_gap_seconds = max_gap_seconds
        self._samples = deque(maxlen=6)
        self.reset()

    def reset(self):
        self.last_timestamp = None
        self._samples.clear()

    def check_time(self, timestamp: float) -> SafetySignal | None:
        if not math.isfinite(timestamp) or timestamp < 0:
            self.reset()
            return SafetySignal('invalid_sample_time')
        previous = self.last_timestamp
        self.last_timestamp = timestamp
        if previous is None:
            return None
        if timestamp <= previous:
            self._samples.clear()
            return SafetySignal('sample_time_not_increasing', timestamp, previous)
        if timestamp - previous > self.max_gap_seconds + 1e-6:
            self._samples.clear()
            return SafetySignal('sample_gap', previous, timestamp)
        return None

    def check_detection(self, timestamp: float, present: bool, *, weak_support: bool) -> SafetySignal | None:
        self._samples.append((timestamp, present, weak_support))
        changes = sum(before[1] != after[1] for before, after in pairwise(self._samples))
        weak_samples = sum(weak for _, _, weak in self._samples)
        if changes >= 3 and weak_samples >= 2:
            return SafetySignal('unstable_detection', self._samples[0][0], timestamp)
        return None
