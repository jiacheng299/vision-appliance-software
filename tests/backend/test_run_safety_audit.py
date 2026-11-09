from types import SimpleNamespace

from app.modules.local_execution import run_safety_audit
from app.modules.local_execution.safety_signals import SafetySignal


def test_reports_are_limited_per_run_and_exclude_input_payload(monkeypatch):
    seconds = iter((10, 11, 12, 20))
    monkeypatch.setattr(run_safety_audit, 'monotonic', lambda: next(seconds))
    records = []
    writer = SimpleNamespace(submit=records.append)
    run = dict(agent_id='task', revision_id='rev', channel_id='channel', source_kind='file',
               config_snapshot={'credentials': 'private'}, source_snapshot={'address': 'private'})
    first = run_safety_audit.RunSafetyAudit(writer, SimpleNamespace(**run, id='run1', source_id='video1'), max_gap_seconds=3)
    second = run_safety_audit.RunSafetyAudit(writer, SimpleNamespace(**run, id='run2', source_id='video2'), max_gap_seconds=3)
    gap = SafetySignal('sample_gap', 2, 8)
    first.report(gap)
    first.report(gap)
    second.report(gap)
    first.report(gap, event_id='event')
    assert [row['source_id'] for row in records] == ['video1', 'video2', 'video1']
    assert records[0]['start_seconds'] == 2 and records[0]['end_seconds'] == 8
    assert records[2]['event_id'] == 'event'
    assert 'private' not in str(records)


def test_reporter_failure_disables_only_this_observer():
    records = []

    def broken(record):
        records.append(record)
        raise OSError('audit failure')

    run = SimpleNamespace(id='run', agent_id='task', revision_id='rev', channel_id='channel',
                          source_id='video', source_kind='file')
    reporter = run_safety_audit.RunSafetyAudit(SimpleNamespace(submit=broken), run, max_gap_seconds=3)
    reporter.report(SafetySignal('sample_gap'))
    reporter.report(SafetySignal('invalid_sample_time'))
    assert len(records) == 1
