"""Diagnostic signals from the local executor's business samples."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SafetySignal:
    reason: str
    start_seconds: float | None = None
    end_seconds: float | None = None


class ObservationWindow:
    def __init__(self, max_gap_seconds: float):
        self.max_gap_seconds = max_gap_seconds
        self.reset()

    def reset(self):
        self.last_timestamp = None

    def check_time(self, timestamp: float) -> SafetySignal | None:
        if not math.isfinite(timestamp) or timestamp < 0:
            self.reset()
            return SafetySignal('invalid_sample_time')
        previous = self.last_timestamp
        self.last_timestamp = timestamp
        if previous is None:
            return None
        if timestamp <= previous:
            return SafetySignal('sample_time_not_increasing', timestamp, previous)
        if timestamp - previous > self.max_gap_seconds + 1e-6:
            return SafetySignal('sample_gap', previous, timestamp)
        return None
