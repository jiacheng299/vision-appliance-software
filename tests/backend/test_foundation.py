import json
import pytest

API = '/api/v1'

def test_settings_persist_validate_and_reject_lost_update(client,app):
    section = client.get(API + '/settings/general').json()
    saved = client.patch(API + '/settings/general',json={'values':{'system_name':'现场测试'},'row_version':section['row_version']})
    assert saved.status_code == 200
    assert client.get(API + '/settings/general').json()['values']['system_name'] == '现场测试'
    assert client.patch(API + '/settings/general',json={'values':{'system_name':'覆盖'},'row_version':section['row_version']}).status_code == 409
    assert client.patch(API + '/settings/general',json={'values':{'unknown':'x'},'row_version':2}).status_code == 422
    security = client.get(API + '/settings/security').json()
    assert client.patch(API + '/settings/security',json={'values':{'camera_allowed_networks':['0.0.0.0/0']},'row_version':security['row_version']}).status_code == 422

def test_camera_credentials_redacted_encrypted_and_archive(client,app):
    secret = 'camera-password-unique-xyz'
    result = client.post(API + '/sources',json={'name':'门口','kind':'camera','address':f'rtsp://alice:{secret}@127.0.0.1:8554/live'})
    assert result.status_code == 200, result.text
    source = result.json()
    assert secret not in json.dumps(source)
    assert 'alice' not in source['address']
    assert source['status'] == 'unverified'
    assert secret.encode() not in (app.state.config.var_root / 'vision.db').read_bytes()
    assert client.patch(API + '/sources/' + source['id'],json={'name':'新名','row_version':1}).status_code == 200
    assert client.patch(API + '/sources/' + source['id'],json={'name':'覆盖','row_version':1}).status_code == 409
    assert client.post(API + '/sources/' + source['id'] + '/preview-sessions').status_code == 503
    assert client.post(API + '/sources/' + source['id'] + '/archive').status_code == 204
    assert client.get(API + '/sources').json()['items'] == []

def test_camera_network_allowlist_and_url_schemes(client):
    for address in ['rtsp://8.8.8.8/live','file:///etc/passwd','rtsp://127.0.0.1/live?token=secret']:
        assert client.post(API + '/sources',json={'name':'blocked','kind':'camera','address':address}).status_code == 422

def test_upload_chunks_are_idempotent_ordered_size_bounded_and_cancelable(client):
    assert client.post(API + '/uploads',json={'filename':'../bad.mp4','size_bytes':3}).status_code == 422
    upload = client.post(API + '/uploads',json={'filename':'clip.mp4','size_bytes':6}).json()
    base = API + '/uploads/' + upload['id']
    assert client.put(base + '/chunks/1',content=b'abc').status_code == 409
    assert client.put(base + '/chunks/0',content=b'abc').json()['received_bytes'] == 3
    assert client.put(base + '/chunks/0',content=b'abc').json()['received_bytes'] == 3
    assert client.put(base + '/chunks/0',content=b'abd').status_code == 409
    assert client.post(base + '/complete',json={}).status_code == 409
    assert client.put(base + '/chunks/1',content=b'defg').status_code == 413
    assert client.put(base + '/chunks/1',content=b'def').json()['received_bytes'] == 6
    queued = client.post(base + '/complete',json={}).json()
    assert queued['state'] == 'probing'
    assert queued['source_id']
    assert client.post(base + '/complete',json={}).json()['source_id'] == queued['source_id']
    assert client.delete(base).status_code == 204
    assert client.get(base).json()['state'] == 'canceled'

def test_worker_fails_invalid_media_truthfully_and_persists(client,app):
    from worker.supervisor import Supervisor
    upload = client.post(API + '/uploads',json={'filename':'broken.mp4','size_bytes':7}).json()
    base = API + '/uploads/' + upload['id']
    client.put(base + '/chunks/0',content=b'not mp4')
    queued = client.post(base + '/complete',json={}).json()
    supervisor = Supervisor(app.state.config)
    assert supervisor.run_once() is True
    result = client.get(base).json()
    assert result['state'] == 'failed'
    assert result['error_code'] in ('dependency_unavailable','invalid_media')
    assert client.get(API + '/sources/' + queued['source_id']).json()['status'] == 'failed'
    assert app.state.config.var_root.as_posix() not in json.dumps(result)

def test_dashboard_runtime_and_empty_extension_contracts(client):
    dashboard = client.get(API + '/dashboard').json()
    assert dashboard['counts'] == {'sources_total':0,'sources_online':0,'active_runs':0,'today_events':0}
    runtime = client.get(API + '/runtime/overview').json()
    assert 0 <= runtime['cpu_percent'] <= 100
    assert runtime['gpu_percent'] is None
    assert runtime['disk']['total_bytes'] > 0
    assert runtime['models'] == []
    assert any(s['key'] == 'models' and s['status'] == 'unavailable' for s in runtime['services'])
    assert client.get(API + '/events').json()['items'] == []
    assert client.get(API + '/runs').json()['items'] == []

def test_websocket_emits_runtime(client):
    with client.websocket_connect(API + '/ws') as ws:
        ws.send_json({'type':'subscribe','topics':['runtime'],'last_sequence':99999})
        message = ws.receive_json()
        assert message['type'] == 'resync_required'
        message = ws.receive_json()
        assert message['type'] == 'runtime'
        assert message['schema_version'] == '1.0'
        assert message['payload']['gpu_percent'] is None
