import json
from threading import Event

from app.modules.local_execution.safety_audit import SafetyAudit, _AuditFile


def test_queue_is_bounded_and_accounts_for_dropped_audits(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    write = _AuditFile.emit

    def blocked_write(handler, record):
        entered.set()
        assert release.wait(3)
        write(handler, record)

    monkeypatch.setattr(_AuditFile, 'emit', blocked_write)
    path = tmp_path / 'logs' / 'model-safety.jsonl'
    audit = SafetyAudit(path, queue_size=1)
    try:
        audit.submit({'reason': 'first'})
        assert entered.wait(3)
        audit.submit({'reason': 'second'})
        audit.submit({'reason': 'overflow'})
    finally:
        release.set()
        audit.close()
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert [row['reason'] for row in rows] == ['first', 'second']
    assert sum(row.get('dropped_since_write', 0) for row in rows) == 1


def test_unwritable_log_location_disables_audit_without_raising(tmp_path, caplog):
    parent = tmp_path / 'logs'
    parent.write_text('not a directory')
    audit = SafetyAudit(parent / 'model-safety.jsonl')
    audit.submit({'reason': 'sample_gap'})
    audit.close()
    assert 'Model safety audit disabled' in caplog.text
    assert str(parent) not in caplog.text


def test_slow_shutdown_abandons_queued_records_after_the_grace_period(tmp_path, monkeypatch):
    entered, release = Event(), Event()
    write = _AuditFile.emit

    def slow_write(handler, record):
        entered.set()
        assert release.wait(5)
        write(handler, record)

    monkeypatch.setattr(_AuditFile, 'emit', slow_write)
    path = tmp_path / 'model-safety.jsonl'
    audit = SafetyAudit(path)
    try:
        audit.submit({'reason': 'in_progress'})
        assert entered.wait(3)
        audit.submit({'reason': 'queued'})
        audit.close()
        assert audit._worker.is_alive()
    finally:
        release.set()
        audit._worker.join(timeout=3)
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    assert [row['reason'] for row in rows] == ['in_progress']
