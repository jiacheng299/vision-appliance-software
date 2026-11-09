"""Build and limit diagnostic records for one video source execution."""
from time import monotonic

from ...shared.models import now
from ..agents.contracts import RunDTO
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
