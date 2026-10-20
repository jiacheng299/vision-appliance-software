import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

API = '/api/v1'


def test_business_and_settings_work_without_accounts(client, app):
    assert client.get(API + '/dashboard').status_code == 200
    snapshot = client.get(API + '/settings/general').json()
    assert client.patch(API + '/settings/general', json={
        'values': {'system_name': '快速验证'}, 'row_version': snapshot['row_version'],
    }).status_code == 200
    with app.state.sessions() as db:
        assert db.scalar(text('SELECT COUNT(*) FROM users')) == 0
        assert db.scalar(text('SELECT COUNT(*) FROM sessions')) == 0
    assert not client.cookies


def test_account_endpoints_are_removed(client):
    assert not any('/auth/' in path for path in client.get('/api/openapi.json').json()['paths'])
    assert client.get(API + '/auth/me').status_code == 404
    assert client.post(API + '/auth/setup', json={'username': 'unused', 'password': 'unused-password'}).status_code in (404, 405)


def test_no_loopback_only_login_mode(app):
    with TestClient(app, base_url='http://workstation.example', client=('192.168.1.20', 50000)) as client:
        assert client.get(API + '/dashboard').status_code == 200


def test_no_cookie_upload_and_media(client, app):
    from app.shared.models import Source
    (app.state.config.var_root / 'media' / 'sample.mp4').write_bytes(b'preview-content')
    with app.state.sessions() as db:
        source = Source(name='预览', kind='file', status='ready', media_key='sample.mp4')
        db.add(source)
        db.commit()
        source_id = source.id
    upload = client.post(API + '/uploads', json={'filename': 'test.mp4', 'size_bytes': 3})
    assert upload.status_code == 200
    upload_id = upload.json()['id']
    assert client.put(f'{API}/uploads/{upload_id}/chunks/0', content=b'abc').status_code == 200
    assert client.post(f'{API}/uploads/{upload_id}/complete', json={}).status_code == 200
    assert client.get(f'{API}/sources/{source_id}/media').content == b'preview-content'
    assert client.post(f'{API}/sources/{source_id}/preview-sessions').status_code == 200


def test_websocket_needs_no_cookie(client):
    with client.websocket_connect(API + '/ws') as ws:
        ws.send_json({'type': 'subscribe', 'topics': ['runtime']})
        assert ws.receive_json()['type'] == 'runtime'


def test_unrelated_website_cannot_send_writes_or_websocket(client):
    assert client.post(API + '/uploads', json={'filename': 'test.mp4', 'size_bytes': 3},
                       headers={'Origin': 'https://other.example'}).status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(API + '/ws', headers={'origin': 'https://other.example'}):
            pass


def test_same_origin_writes_work_on_any_host(app):
    with TestClient(app, base_url='http://workstation.example:8000', client=('192.168.1.20', 50000)) as client:
        assert client.post(API + '/uploads', json={'filename': 'test.mp4', 'size_bytes': 3},
                           headers={'Origin': 'http://workstation.example:8000'}).status_code == 200
        assert client.post(API + '/uploads', json={'filename': 'test.mp4', 'size_bytes': 3},
                           headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403


def test_old_security_settings_upgrade_without_losing_networks(app):
    from app.main import create_app
    from app.shared.models import Setting
    with app.state.sessions() as db:
        record = db.get(Setting, 'security')
        record.values = {'session_timeout_minutes': 480, 'camera_allowed_networks': ['192.168.1.0/24']}
        db.commit()
    upgraded = create_app(var_root=app.state.config.var_root, testing=True)
    with TestClient(upgraded) as client:
        setting = client.get(API + '/settings/security').json()
        assert setting['values'] == {'camera_allowed_networks': ['192.168.1.0/24']}
        assert client.patch(API + '/settings/security', json={
            'values': {'camera_allowed_networks': ['127.0.0.0/8']}, 'row_version': setting['row_version'],
        }).status_code == 200
