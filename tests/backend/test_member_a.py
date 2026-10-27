"""A-01--A-10: durable registry plus grouped-source creation using B's public APIs."""
from copy import deepcopy
import hashlib
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.modules.models.integrations import ModelServices, DemoModelServices
from app.modules.models.schemas import Deployment

API = '/api/v1'


def post(c, path, body=None, key=None):
    return c.post(API+path, json=body, headers={'Idempotency-Key': key or str(uuid4())})


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO', 'true')
    app = create_app(var_root=tmp_path, testing=True)
    with TestClient(app) as c:
        assert post(c, '/agent-demo/seed').status_code == 200
        yield c, app


def definition(c, version='1.0', data=b'inert bytes; never execute'):
    response = c.post(API+'/model-files', params={'filename': 'model.unknown'}, content=data, headers={'Content-Type': 'application/octet-stream'})
    assert response.status_code == 201, response.text
    file = response.json()
    assert file['checksum'] == hashlib.sha256(data).hexdigest()
    return {'name': '区域人员', 'version': version, 'runtime_type': 'unselected-runtime', 'file_id': file['id'], 'template': {
        'name': '区域模板', 'version': version, 'targets': ['person'], 'rules': ['dwell', 'intrusion'],
        'requires_region': ['dwell', 'intrusion'], 'requires_duration': ['dwell'], 'defaults': {}, 'limitations': ['仅供测试']}}


def imported(c, version='1.0'):
    body = definition(c, version)
    result = post(c, '/models', body)
    assert result.status_code == 201, result.text
    return result.json()


def verified(c, m):
    result = post(c, f"/models/{m['id']}/versions/{m['version']}/verify", {'row_version': m['row_version']})
    assert result.status_code == 200, result.text
    return result.json()


def config(c, reference=None):
    sources = c.get(API+'/sources').json()['items']
    ref = reference or next(i['reference'] for i in c.get(API+'/capabilities/models').json()['items'] if 'person' in i['targets'] and 'dwell' in i['rules'])
    return {'schema_version': '1.0', 'channels': [{'channel_id': 'group-1', 'name': '北门组', 'sources': [
        {'source_id': s['id'], 'regions': [{'id': 'roi', 'points': [[0, 0], [1, 0], [0, 1]]}]} for s in sources[:2]],
        'requirement_text': '有人在区域停留超过30秒报警', 'target': 'person', 'rule': 'dwell', 'duration_seconds': 30, 'capability_ref': ref}]}


def create_agent(c, cfg, key=None):
    response = post(c, '/agents', {'name': 'A创建的多视频任务', 'config': cfg}, key)
    assert response.status_code == 201, response.text
    return response.json()


def publish(c, agent):
    revision = agent['latest_revision']
    response = post(c, f"/revisions/{revision['id']}/validations", {'row_version': revision['row_version']})
    assert response.status_code == 201, response.text
    value = response.json()
    revision = c.get(API+'/revisions/'+revision['id']).json()
    response = post(c, f"/revisions/{revision['id']}/confirmations", {'row_version': revision['row_version'], 'validation_id': value['id'], 'config_hash': value['config_hash'], 'limitations_acknowledged': True})
    assert response.status_code == 200, response.text
    return response.json()


def test_real_import_pending_and_no_mock_leak(client, app):
    body = definition(client)
    key = str(uuid4())
    first = post(client, '/models', body, key)
    again = post(client, '/models', body, key)
    assert first.status_code == 201 and again.json() == first.json()
    changed = dict(body, name='different')
    assert post(client, '/models', changed, key).status_code == 409
    m = verified(client, first.json())
    assert m['validation'] == 'pending' and m['data_origin'] == 'real'
    assert client.get(API+'/capabilities/models').json()['items'] == []
    assert client.get(API+'/agent-services/capabilities').json()['items'] == []
    assert client.get(API+'/llm/deployments').json()['items'] == []
    assert post(client, '/requirements/parse', {'requirement_text': '有人停留太久报警'}).status_code == 503
    assert client.get(API+'/models').json()['items'][0]['id'] == m['id']
    with TestClient(create_app(var_root=app.state.config.var_root, testing=True)) as restarted:
        assert restarted.get(API+'/models/'+m['id']).json()['checksum'] == m['checksum']


def test_untrusted_requests_cannot_mark_model_passed(client):
    body = definition(client)
    assert post(client, '/models', dict(body, validation='passed')).status_code == 422
    body['template']['requires_duration'] = ['not-declared']
    assert post(client, '/models', body).status_code == 422
    assert client.get(API+'/capabilities/models').json()['items'] == []


def test_model_file_validation_and_size(client, app):
    assert client.post(API+'/model-files', params={'filename': '../escape.pt'}, content=b'x').status_code == 422
    assert client.post(API+'/model-files', params={'filename': 'empty.pt'}, content=b'').status_code == 422
    app.state.config.max_model_file_bytes = 3
    assert client.post(API+'/model-files', params={'filename': 'large.pt'}, content=b'abcd').status_code == 413
    assert not list((app.state.config.var_root/'model-files').glob('*.part'))


def test_tampered_file_fails_checksum(demo):
    c, app = demo
    m = imported(c)
    (app.state.config.var_root/'model-files'/m['file_id']).write_bytes(b'tampered')
    m = verified(c, m)
    assert m['validation'] == 'failed'
    assert not any(i['reference']['model_id'] == m['id'] for i in c.get(API+'/capabilities/models').json()['items'])


def test_versions_keep_pairing_and_previous_snapshots(demo):
    c, app = demo
    first = verified(c, imported(c))
    body = definition(c, '2.0')
    path = f"/models/{first['id']}/versions"
    second = post(c, path, body).json()
    assert second['template_id'] == first['template_id']
    assert second['validation'] == 'pending'
    assert post(c, path, body).status_code == 409
    body['version'] = '3.0'
    assert post(c, path, body).status_code == 409  # reused template version forbidden
    assert c.get(API+'/models/'+first['id'], params={'version': '1.0'}).json() == first
    check = c.get(API+'/capabilities/models').json()
    ref = next(i['reference'] for i in check['items'] if i['reference']['model_id'] == first['id'])
    assert post(c, '/capabilities/validate', {'capability_ref': ref, 'target': 'person', 'rule': 'dwell'}).json()['valid']
    ref['model_version'] = '2.0'
    assert not post(c, '/capabilities/validate', {'capability_ref': ref, 'target': 'person', 'rule': 'dwell'}).json()['valid']
    assert post(c, f"/models/{first['id']}/versions/1.0/verify", {'row_version': 1}).status_code == 409
    page = c.get(API+'/models', params={'limit': 1}).json()
    assert page['next_cursor']
    next_page = c.get(API+'/models', params={'limit': 1, 'cursor': page['next_cursor']}).json()
    assert next_page['items'][0]['version'] != page['items'][0]['version']


def test_parse_missing_duration_and_selection_snapshot(demo):
    c, _ = demo
    assert post(c, '/requirements/parse', {'requirement_text': '有人停留太久报警'}).status_code == 503
    body = {'deployment_id': 'MOCK-local-parser', 'row_version': 0}
    assert c.put(API+'/llm/selections/requirement_parse', json=body).status_code == 200
    first = post(c, '/requirements/parse', {'requirement_text': '有人停留太久报警'}).json()
    assert first['duration_seconds'] is None and first['missing_conditions']
    assert first['deployment_version'] == '1.0'
    assert c.put(API+'/llm/selections/requirement_parse', json=body).status_code == 409
    assert c.put(API+'/llm/selections/requirement_parse', json={'deployment_id': 'MOCK-multimodal', 'row_version': 1}).status_code == 422
    assert c.put(API+'/llm/selections/requirement_parse', json={'deployment_id': 'MOCK-local-parser-2', 'row_version': 1}).status_code == 200
    next_value = post(c, '/requirements/parse', {'requirement_text': '有人停留30秒报警'}).json()
    assert next_value['duration_seconds'] == 30 and next_value['deployment_version'] == '2.0'
    assert first['deployment_version'] == '1.0'


def test_grouped_conditions_are_checked_per_video_and_stale_validation_blocked(demo):
    c, _ = demo
    cfg = config(c)
    cfg['channels'][0]['duration_seconds'] = None
    a = create_agent(c, cfg)
    r = a['latest_revision']
    value = post(c, '/requirements/evaluate', {'config': cfg}).json()
    assert value['verdict'] == 'clarification_required'
    cfg['channels'][0]['duration_seconds'] = 30
    cfg['channels'][0]['sources'][1]['regions'] = []
    assert post(c, '/requirements/evaluate', {'config': cfg}).json()['verdict'] == 'clarification_required'
    cfg['channels'][0]['sources'][1]['regions'] = cfg['channels'][0]['sources'][0]['regions']
    r = c.patch(API+'/revisions/'+r['id'], json={'row_version': r['row_version'], 'config': cfg}).json()
    validation = post(c, '/revisions/'+r['id']+'/validations', {'row_version': r['row_version']}).json()
    assert validation['verdict'] == 'executable'
    r = c.get(API+'/revisions/'+r['id']).json()
    cfg['channels'][0]['duration_seconds'] = 60
    r = c.patch(API+'/revisions/'+r['id'], json={'row_version': r['row_version'], 'config': cfg}).json()
    assert post(c, '/revisions/'+r['id']+'/confirmations', {'row_version': r['row_version'], 'validation_id': validation['id'], 'config_hash': validation['config_hash'], 'limitations_acknowledged': True}).status_code == 409
    cfg['channels'][0]['rule'] = 'flight'
    assert post(c, '/requirements/evaluate', {'config': cfg}).json()['verdict'] == 'unsupported'


def test_imported_mock_capability_creates_two_runs_without_duplicates_and_archive_blocks(demo):
    c, app = demo
    m = verified(c, imported(c))
    cap = next(i for i in c.get(API+'/capabilities/models').json()['items'] if i['reference']['model_id'] == m['id'])
    cfg = config(c, cap['reference'])
    key = str(uuid4()); a = create_agent(c, cfg, key)
    assert create_agent(c, cfg, key)['id'] == a['id']
    r = publish(c, a)
    body = {'revision_id': r['id'], 'channel_ids': ['group-1'], 'expected_active_run_ids': []}
    path = f"/agents/{a['id']}/run-groups"; key = str(uuid4())
    op = post(c, path, body, key).json()
    assert post(c, path, body, key).json()['id'] == op['id']
    app.state.agent_services.advance(5)
    result = c.get(API+f"/agents/{a['id']}/operations/{op['id']}").json()
    assert result['state'] == 'succeeded', result
    runs = c.get(API+f"/agents/{a['id']}/workspace").json()['runs']
    assert len(runs) == 2 and len({run['source_id'] for run in runs}) == 2
    archive = f"/models/{m['id']}/versions/{m['version']}/archive"
    assert post(c, archive, {'row_version': m['row_version'], 'acknowledge_history': True}).status_code == 409
    stop = post(c, f"/agents/{a['id']}/channels/group-1/stop").json(); app.state.agent_services.advance(5)
    assert c.get(API+f"/agents/{a['id']}/operations/{stop['id']}").json()['state'] == 'succeeded'
    assert post(c, archive, {'row_version': m['row_version']}).json()['error']['code'] == 'model_history_confirmation'
    assert post(c, archive, {'row_version': m['row_version'], 'acknowledge_history': True}).status_code == 200
    assert not any(i['reference']['model_id'] == m['id'] for i in c.get(API+'/capabilities/models').json()['items'])
    assert c.get(API+'/revisions/'+r['id']).json()['config']['channels'][0]['capability_ref'] == cap['reference']


def test_real_runtime_absent_still_allows_drafts_but_not_execution(client):
    a = create_agent(client, {'channels': []})
    assert client.get(API+'/agents/'+a['id']).status_code == 200
    assert post(client, f"/agents/{a['id']}/run-groups", {'revision_id': a['latest_revision']['id'], 'channel_ids': ['x']}).status_code != 202


def test_mock_model_adapter_requires_explicit_mode(tmp_path):
    with pytest.raises(RuntimeError, match='isolated demo'):
        create_app(var_root=tmp_path, model_services=DemoModelServices())


def test_recording_interval_rejected_and_draft_restored(demo):
    c, app = demo
    cfg = config(c)
    file_source = next(s for s in c.get(API+'/sources').json()['items'] if s['kind'] == 'file')
    binding = cfg['channels'][0]['sources'][0]
    binding['source_id'] = file_source['id']
    cfg['channels'][0]['sources'] = [binding]
    binding['start_media_ms'] = 0
    binding['end_media_ms'] = file_source['duration_ms'] + 1
    response = post(c, '/agents', {'name': '坏区间', 'config': cfg})
    assert response.status_code == 422
    binding['end_media_ms'] = min(file_source['duration_ms'], 10000)
    a = create_agent(c, cfg)
    restored = c.get(API+'/agents/'+a['id']).json()
    assert restored['latest_revision']['config']['channels'][0]['sources'][0]['end_media_ms'] == binding['end_media_ms']


def test_real_registry_port_requires_analysis_and_checks_published_references(tmp_path):
    """Trusted algorithm stub tests the port; it is not a shipped real detector."""
    class TrustedStub(ModelServices):
        def verify(self, definition, path, checksum):
            assert path.read_bytes().startswith(b'inert')
            return 'passed', 'trusted verifier test double'

    app = create_app(var_root=tmp_path, testing=True, model_services=TrustedStub())
    with TestClient(app) as c:
        m = verified(c, imported(c))
        assert m['data_origin'] == 'real' and m['validation'] == 'passed'
        assert len(c.get(API+'/capabilities/models').json()['items']) == 1
        from app.shared.models import Source
        with app.state.sessions() as db:
            db.add(Source(id='file', name='fixture', kind='file', status='ready', duration_ms=100000, width=1280, height=720))
            db.commit()
        cfg = config(c)
        assert post(c, '/requirements/evaluate', {'config': cfg}).status_code == 503
        a = create_agent(c, cfg)
        # A published reference without an available runtime must fail closed.
        from app.modules.agents.models import AgentRevision
        with app.state.sessions() as db:
            db.get(AgentRevision, a['latest_revision']['id']).state = 'published'
            db.commit()
        response = post(c, f"/models/{m['id']}/versions/{m['version']}/archive", {'row_version': m['row_version'], 'acknowledge_history': True})
        assert response.status_code == 409 and response.json()['error']['code'] == 'model_in_use'
