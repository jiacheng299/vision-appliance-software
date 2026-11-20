"""大模型辅助画像分析：设置明文往返、抽帧契约、动态属性写入与官方来源边界。"""
import base64
import json

import cv2
import httpx
import numpy as np
import pytest

from app.modules.semantics import assistant
from app.modules.semantics.llm import ProfileLlm
from app.shared.errors import Error
from app.shared.models import Source

_, _encoded = cv2.imencode('.jpg', np.random.default_rng(3).integers(
    0, 255, (48, 64, 3), dtype=np.uint8))
JPEG = _encoded.tobytes()
FRAMES = [JPEG, JPEG, JPEG]

ANALYSIS = {
    'lighting': {'label': 'bright', 'confidence': 0.8},
    'weather': {'label': 'overcast', 'confidence': 0.6},
    'season_appearance': None,
    'camera_pose': {'label': 'fixed', 'confidence': 0.9},
    'background_texture': {'label': 'dense', 'confidence': 0.5},
    'occlusion': {'label': 'none', 'confidence': 0.7},
}


def envelope(content: dict) -> httpx.MockTransport:
    body = json.dumps({'choices': [{'message': {'content': json.dumps(content)}}]},
                      ensure_ascii=False).encode('utf-8')
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={'Content-Encoding': 'identity'}, content=body)
    return httpx.MockTransport(handler)


def fake_reader(*args, **kwargs):
    return list(FRAMES)


@pytest.fixture
def seeded(app):
    with app.state.sessions() as db:
        db.add(Source(id='cam', name='摄像头', kind='camera', status='online',
                      width=960, height=540, fps=15.0))
        db.commit()
    return app


def configure(client, provider='kimi', key='sk-test', model='kimi-latest'):
    current = client.get('/api/v1/settings/llm').json()
    saved = client.patch('/api/v1/settings/llm', json={'row_version': current['row_version'],
        'values': {'provider': provider, 'api_key': key, 'model': model}})
    assert saved.status_code == 200, saved.text
    return saved.json()


def test_llm_settings_roundtrip_plaintext_and_initialized(client):
    body = client.get('/api/v1/settings/llm')
    assert body.status_code == 200
    saved = configure(client, key='sk-kimi-plaintext')
    assert saved['values']['api_key'] == 'sk-kimi-plaintext'
    assert saved['values']['provider'] == 'kimi'


def test_analyze_writes_llm_attributes_and_resolution(seeded, client):
    app = seeded
    configure(client)
    with app.state.sessions() as db:
        profile, written = assistant.analyze_profile(
            db, app.state.config, 'cam', frame_reader=fake_reader, transport=envelope(ANALYSIS))
    assert set(written) == {'lighting', 'weather', 'camera_pose', 'background_texture', 'occlusion'}
    rows = {row.key: row for row in profile.attributes}
    assert rows['lighting'].value['label'] == 'bright'
    assert rows['lighting'].source_kind == 'probe'
    assert rows['lighting'].tau_seconds == 1800.0
    assert rows['lighting'].hard_expiry_at is not None
    assert rows['occlusion'].value['label'] == 'none'
    assert 'season_appearance' not in rows
    assert profile.intrinsic['resolution'] == '960x540'


def test_analyze_requires_configured_key(seeded):
    app = seeded
    with app.state.sessions() as db:
        with pytest.raises(Error) as failure:
            assistant.analyze_profile(db, app.state.config, 'cam', frame_reader=fake_reader,
                                      transport=envelope(ANALYSIS))
    assert failure.value.code == 'llm_not_configured'


def test_deepseek_official_api_refuses_frame_analysis(seeded, client):
    app = seeded
    configure(client, provider='deepseek', model='deepseek-chat')
    with app.state.sessions() as db:
        with pytest.raises(Error) as failure:
            assistant.analyze_profile(db, app.state.config, 'cam', frame_reader=fake_reader,
                                      transport=envelope(ANALYSIS))
    assert failure.value.code == 'llm_no_vision'


def test_invalid_llm_json_becomes_invalid_response(seeded, client):
    app = seeded
    configure(client)
    transport = envelope({'unexpected': True})
    with app.state.sessions() as db:
        with pytest.raises(Error) as failure:
            assistant.analyze_profile(db, app.state.config, 'cam', frame_reader=fake_reader,
                                      transport=transport)
    assert failure.value.code == 'llm_invalid_response'


def test_client_sends_bearer_and_images(seeded, client):
    app = seeded
    saved = configure(client, key='sk-open-platform')
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen['authorization'] = request.headers.get('Authorization')
        payload = json.loads(request.content)
        seen['images'] = [part['type'] for part in payload['messages'][1]['content']]
        seen['model'] = payload['model']
        body = json.dumps({'choices': [{'message': {'content': json.dumps(ANALYSIS)}}]},
                          ensure_ascii=False).encode('utf-8')
        return httpx.Response(200, headers={'Content-Encoding': 'identity'}, content=body)
    with app.state.sessions() as db:
        assistant.analyze_profile(db, app.state.config, 'cam', frame_reader=fake_reader,
                                  transport=httpx.MockTransport(handler))
    assert seen['authorization'] == 'Bearer sk-open-platform'
    assert seen['images'] == ['image_url', 'image_url', 'image_url']
    assert seen['model'] == saved['values']['model']


def test_analyze_endpoint_returns_written_keys(client, seeded, monkeypatch):
    from app.modules.semantics import routes as semantics_routes
    from app.modules.semantics.schemas import ProfileView
    captured = {}
    def fake_analyze(db, config, source_id, gateway=None, **kwargs):
        captured['source_id'] = source_id
        return ProfileView(source_id=source_id, view_version='v1', version=2, intrinsic={},
                           runtime={}, attributes=[], evaluated_at=0, updated_at=''), ['lighting']
    monkeypatch.setattr(semantics_routes, 'analyze_profile', fake_analyze)
    response = client.post('/api/v1/sources/cam/semantic-profile/analyze')
    assert response.status_code == 200
    body = response.json()
    assert captured['source_id'] == 'cam'
    assert body['analyzed'] == ['lighting']
    assert body['profile']['source_id'] == 'cam'


def test_unauthorized_key_becomes_auth_error(seeded, client):
    app = seeded
    configure(client, key='sk-kimi-invalid')
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={'error': {'message': 'Invalid Authentication'}})
    with app.state.sessions() as db:
        with pytest.raises(Error) as failure:
            assistant.analyze_profile(db, app.state.config, 'cam', frame_reader=fake_reader,
                                      transport=httpx.MockTransport(handler))
    assert failure.value.code == 'llm_auth_invalid'


def test_kimi_subscription_key_uses_anthropic_endpoint(seeded, client):
    app = seeded
    configure(client, key='sk-kimi-subscription')
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen['url'] = str(request.url)
        seen['api_key'] = request.headers.get('x-api-key')
        payload = json.loads(request.content)
        seen['model'] = payload['model']
        seen['system'] = payload['system']
        seen['blocks'] = [part['type'] for part in payload['messages'][0]['content']]
        body = json.dumps({'content': [
            {'type': 'thinking', 'thinking': '推理过程'},
            {'type': 'text', 'text': json.dumps(ANALYSIS)}]},
            ensure_ascii=False).encode('utf-8')
        return httpx.Response(200, headers={'Content-Encoding': 'identity'}, content=body)
    with app.state.sessions() as db:
        profile, written = assistant.analyze_profile(
            db, app.state.config, 'cam', frame_reader=fake_reader,
            transport=httpx.MockTransport(handler))
    assert 'lighting' in written
    assert seen['url'].startswith('https://api.kimi.com/coding/v1/messages')
    assert seen['api_key'] == 'sk-kimi-subscription'
    assert seen['model'] == 'kimi-latest'
    assert seen['blocks'] == ['image', 'image', 'image']
    assert 'lighting' in seen['system']


def test_rejects_non_jpeg_frames(seeded, client):
    app = seeded
    configure(client)
    with app.state.sessions() as db:
        with pytest.raises(Error) as failure:
            assistant.analyze_profile(db, app.state.config, 'cam',
                                      frame_reader=lambda *a, **k: [b'not-a-jpeg'],
                                      transport=envelope(ANALYSIS))
    assert failure.value.code == 'llm_frame_invalid'
