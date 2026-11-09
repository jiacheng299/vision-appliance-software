import json


def audit_row(**changes):
    return {
        'agent_id': 'task', 'source_id': 'video', 'run_id': 'run', 'channel_id': 'channel',
        'source_kind': 'file', 'observed_at': '2026-11-09T03:00:00Z',
        'reason': 'sample_gap', 'start_seconds': 30, 'end_seconds': 59,
        'event_id': None, 'private_path': 'private',
    } | changes


def test_read_checks_bounds_the_tail_and_projects_known_fields(tmp_path):
    from app.modules.local_execution.trust_checks import MAX_TAIL_BYTES, read_trust_checks

    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'model-safety.jsonl.1').write_text(json.dumps(audit_row(run_id='rotated')) + '\n')
    lines = [audit_row(run_id='outside-tail'), audit_row(run_id='recent'),
             audit_row(agent_id='another-task'), audit_row(source_id='another-source'),
             audit_row(reason='arbitrary_log_message'), audit_row(start_seconds=float('nan'))]
    data = [json.dumps(lines[0]), 'x' * MAX_TAIL_BYTES, *map(json.dumps, lines[1:]), '{"partial":']
    (logs / 'model-safety.jsonl').write_text('\n'.join(data), encoding='utf-8')

    records = read_trust_checks(tmp_path, 'task', 'video')
    assert [record.run_id for record in records] == ['recent', 'rotated']
    assert 'private_path' not in records[0].model_dump()
