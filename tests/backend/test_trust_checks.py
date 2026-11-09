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


def test_task_checks_verify_run_scope_and_only_link_its_alarm(client, app):
    from app.modules.agents.models import Agent
    from app.modules.local_execution.models import LocalEvent, LocalRun

    def run(identifier, source_id, actor='workspace'):
        return LocalRun(id=identifier, agent_id='task', source_id=source_id, actor_id=actor,
                        channel_id='channel', state='completed', payload={'source_kind': 'file'})

    with app.state.sessions() as db:
        db.add(Agent(id='task', name='测试任务', owner_id='workspace'))
        db.add_all([run('run', 'video'), run('second', 'video2'), run('foreign', 'video', 'other')])
        db.add(LocalEvent(id='alarm', agent_id='task', actor_id='workspace', run_id='run', payload={}))
        db.commit()

    url = '/api/v1/agents/task/trust-checks'
    assert client.get(url).json() == []
    logs = app.state.config.var_root / 'logs'
    logs.mkdir()
    rows = [audit_row(event_id='alarm', reason='evidence_unavailable'),
            audit_row(run_id='second', source_id='video2', event_id='alarm'),
            audit_row(run_id='foreign'), audit_row(channel_id='invalid'), audit_row(run_id='missing')]
    (logs / 'model-safety.jsonl').write_text('\n'.join(map(json.dumps, rows)), encoding='utf-8')

    response = client.get(url)
    assert response.status_code == 200, response.text
    assert [(row['source_id'], row['event_id']) for row in response.json()] == [('video2', None), ('video', 'alarm')]
    filtered = client.get(url, params={'source_id': 'video2'}).json()
    assert [row['source_id'] for row in filtered] == ['video2']
    assert client.get('/api/v1/agents/unknown/trust-checks').status_code == 404
