"""Build and limit diagnostic records for one video source execution."""
from time import monotonic

from ...shared.models import now
from ..agents.contracts import EventDetail, RunDTO
from ..agents.schemas import ChannelSource
from .safety_audit import SafetyAudit
from .safety_signals import ObservationWindow, SafetySignal


class RunSafetyAudit:
    def __init__(self, writer: SafetyAudit, run: RunDTO, *, max_gap_seconds: float):
        self._writer = writer
        self._window = ObservationWindow(max_gap_seconds)
        self._scope = {
            'run_id': run.id,
            'agent_id': run.agent_id,
            'revision_id': run.revision_id,
            'channel_id': run.channel_id,
            'source_id': run.source_id,
            'source_kind': run.source_kind,
        }
        self._next_report: dict[str, float] = {}

    def check_time(self, timestamp: float):
        self.report(self._window.check_time(timestamp))

    def interrupted(self):
        self.report(SafetySignal('observation_interrupted', self._window.last_timestamp))
        self._window.reset()

    def check_detection(self, timestamp, count, boxes, *, threshold, required_count):
        if self._writer is None:
            return
        present = count >= required_count
        weak_support = False
        if present:
            weak_count = 0
            for box in boxes:
                score = box.get('confidence')
                if isinstance(score, (int, float)) and threshold <= score <= threshold + .05:
                    weak_count += 1
            weak_support = count - weak_count < required_count
        self.report(self._window.check_detection(timestamp, present, weak_support=weak_support))

    def check_event(self, event: EventDetail, binding: ChannelSource):
        start, end = event.start_media_ms, event.end_media_ms
        reasons = []
        if any(getattr(event, key) != value for key, value in self._scope.items() if key != 'source_kind'):
            reasons.append('event_scope_mismatch')
        if self._scope['source_kind'] == 'file':
            if (start is None or end is None or binding.end_media_ms is None
                    or not (binding.start_media_ms or 0) <= start <= end <= binding.end_media_ms):
                reasons.append('event_media_range_invalid')
        elif start is not None or end is not None:
            reasons.append('event_media_range_invalid')
        if event.evidence_status != 'ready' or not any(item.state == 'ready' for item in event.evidence):
            reasons.append('evidence_unavailable')
        for reason in reasons:
            signal = SafetySignal(reason, start / 1000 if start is not None else None,
                                  end / 1000 if end is not None else None)
            self.report(signal, event_id=event.id)

    def report(self, signal: SafetySignal | None, *, event_id: str | None = None):
        if self._writer is None or signal is None:
            return
        try:
            current = monotonic()
            if current < self._next_report.get(signal.reason, 0):
                return
            self._next_report[signal.reason] = current + 10
            self._writer.submit({
                **self._scope,
                'policy_version': 1,
                'observed_at': now(),
                'reason': signal.reason,
                'start_seconds': signal.start_seconds,
                'end_seconds': signal.end_seconds,
                'event_id': event_id,
            })
        except Exception:
            # Observability is best effort and must never abort the monitoring run.
            self._writer = None
