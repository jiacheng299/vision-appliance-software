import gzip
import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

API = '/api/v1'
KEY = 'unit-test-deepseek-secret'


@pytest.fixture
def matcher_app(tmp_path, monkeypatch):
    monkeypatch.setenv('VISION_AGENT_DEMO', 'true')
    monkeypatch.setenv('VISION_DEEPSEEK_API_KEY', KEY)
    monkeypatch.setenv('VISION_DEEPSEEK_MODEL', 'deepseek-flash')
    monkeypatch.setenv('VISION_DEEPSEEK_MATCH_THRESHOLD', '.8')
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    from app.main import create_app
    app = create_app(var_root=tmp_path, testing=True)
    with TestClient(app) as client:
        yield app, client


def candidate(app, *, state='published', archived=False, name='人员在岗', description='区域无人持续30秒报警', config=None):
    from app.modules.agent_templates.models import AgentTemplate, AgentTemplateRevision
    from app.shared.models import now
    template_id, revision_id = str(uuid4()), str(uuid4())
    with app.state.sessions() as db:
        db.add(AgentTemplate(id=template_id, name=name, description=description,
                             archived_at=now() if archived else None))
        db.flush()
        db.add(AgentTemplateRevision(id=revision_id, template_id=template_id, revision_no=1,
            state=state, config=config or {'default_target': 'person', 'default_rule': 'absence',
                'parameters': [{'key': 'duration_seconds', 'value': 30, 'required': False}]}))
        db.commit()
    return template_id, revision_id


def decision(ids, **overrides):
    result = {'status': 'matched', 'template_id': ids[0], 'template_revision_id': ids[1],
              'confidence': .95, 'reason': '已覆盖人员在岗检测需求', 'uncovered_requirements': []}
    return result | overrides


def upstream(monkeypatch, result=None, *, status=200, handler=None):
    requests = []
    def respond(transport, request):
        requests.append(request)
        if handler:
            return handler(request)
        return httpx.Response(status, json={'choices': [{'message': {'content': json.dumps(result)}}]}, request=request)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', respond)
    return requests


def match(client, text='监测人员在岗，连续无人30秒报警'):
    return client.post(API + '/agent-templates/match', json={'requirement_text': text})


def test_status_and_missing_key_are_explicit_and_never_expose_secrets(matcher_app):
    app, client = matcher_app
    status = client.get(API + '/agent-template-matcher')
    assert status.status_code == 200
    assert status.json() == {'configured': True, 'provider': 'deepseek', 'model': 'deepseek-flash', 'threshold': .8}
    app.state.config.deepseek_api_key = None
    assert client.get(API + '/agent-template-matcher').json()['configured'] is False
    response = match(client)
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'template_matcher_not_configured'
    assert KEY not in response.text + status.text


def test_match_returns_only_a_published_candidate_and_safe_request(matcher_app, monkeypatch):
    app, client = matcher_app
    ids = candidate(app)
    excluded = [candidate(app, state='draft'), candidate(app, archived=True)]
    requests = upstream(monkeypatch, decision(ids))
    # A malformed global proxy must not affect the dedicated HTTPS client.
    monkeypatch.setenv('HTTPS_PROXY', 'invalid-proxy-scheme://should-not-be-used')
    response = match(client)
    assert response.status_code == 200, response.text
    assert response.json() == decision(ids) | {'provider': 'deepseek', 'model': 'deepseek-flash'}
    assert len(requests) == 1
    assert str(requests[0].url) == 'https://api.deepseek.com/chat/completions'
    assert requests[0].headers['authorization'] == 'Bearer ' + KEY
    body = json.loads(requests[0].content)
    assert body['model'] == 'deepseek-flash'
    assert body['response_format'] == {'type': 'json_object'}
    assert body['thinking'] == {'type': 'disabled'}
    assert ids[0] in requests[0].content.decode()
    for template_id, _ in excluded:
        assert template_id not in requests[0].content.decode()
    assert KEY not in requests[0].content.decode()


@pytest.mark.parametrize('changes', [
    {'confidence': .79},
    {'uncovered_requirements': ['还需要人脸身份识别']},
    {'status': 'no_match'},
])
def test_low_confidence_or_uncovered_requirement_never_selects_a_template(matcher_app, monkeypatch, changes):
    app, client = matcher_app
    ids = candidate(app)
    upstream(monkeypatch, decision(ids, **changes))
    response = match(client)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'no_match'
    assert result['template_id'] is result['template_revision_id'] is None


def test_no_eligible_candidates_returns_no_match_without_calling_provider(matcher_app, monkeypatch):
    app, client = matcher_app
    candidate(app, state='draft')
    candidate(app, archived=True)
    requests = upstream(monkeypatch, {})
    response = match(client)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'no_match'
    assert response.json()['confidence'] == 0
    assert requests == []


def test_long_requirement_with_no_candidates_remains_a_valid_no_match(matcher_app):
    _, client = matcher_app
    response = match(client, '在岗监测' * 400)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'no_match'


def test_latest_draft_description_does_not_replace_published_semantics(matcher_app, monkeypatch):
    app, client = matcher_app
    ids = candidate(app, name='未发布的人脸识别', description='draft-face-only', config={
        'title': '人员在岗', 'summary': 'published-presence-only',
        'default_target': 'person', 'default_rule': 'absence', 'parameters': []})
    requests = upstream(monkeypatch, decision(ids))
    response = match(client)
    assert response.status_code == 200, response.text
    body = requests[0].content.decode()
    assert 'published-presence-only' in body
    assert 'draft-face-only' not in body


def test_custom_threshold_controls_selection_and_custom_model_is_used(matcher_app, monkeypatch):
    app, client = matcher_app
    app.state.config.deepseek_model = 'deepseek-custom'
    app.state.config.deepseek_match_threshold = .9
    ids = candidate(app)
    requests = upstream(monkeypatch, decision(ids, confidence=.85))
    response = match(client)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'no_match'
    assert response.json()['model'] == 'deepseek-custom'
    assert json.loads(requests[0].content)['model'] == 'deepseek-custom'


@pytest.mark.parametrize('changes', [
    {'template_id': 'invented'}, {'template_revision_id': 'invented'},
    {'template_id': None}, {'confidence': 1.1}, {'confidence': -1},
    {'confidence': '0.99'}, {'confidence': True}, {'status': 'execute'},
    {'uncovered_requirements': 'none'}, {'unexpected': 'field'},
])
def test_untrusted_decisions_fail_closed(matcher_app, monkeypatch, changes):
    app, client = matcher_app
    ids = candidate(app)
    upstream(monkeypatch, decision(ids, **changes))
    response = match(client)
    assert response.status_code == 502, response.text
    assert response.json()['error']['code'] == 'template_matcher_invalid_response'


def test_candidate_must_still_be_available_after_provider_response(matcher_app, monkeypatch):
    app, client = matcher_app
    ids = candidate(app)
    def archive_during_request(request):
        from app.modules.agent_templates.models import AgentTemplate
        from app.shared.models import now
        with app.state.sessions() as db:
            db.get(AgentTemplate, ids[0]).archived_at = now()
            db.commit()
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(decision(ids))}}]}, request=request)
    upstream(monkeypatch, handler=archive_during_request)
    response = match(client)
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'template_matcher_candidates_changed'


@pytest.mark.parametrize('failure, expected', [('timeout', 504), ('http', 502), ('redirect', 502), ('malformed', 502), ('oversized', 502)])
def test_upstream_errors_are_bounded_and_do_not_leak_key(matcher_app, monkeypatch, caplog, failure, expected):
    app, client = matcher_app
    candidate(app)
    def fail(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout(KEY, request=request)
        if failure == 'http':
            return httpx.Response(429, text=KEY, request=request)
        if failure == 'redirect':
            return httpx.Response(302, headers={'Location': 'https://attacker.invalid/' + KEY}, request=request)
        if failure == 'oversized':
            return httpx.Response(200, content=b'x' * 70000, request=request)
        return httpx.Response(200, text=KEY, request=request)
    requests = upstream(monkeypatch, handler=fail)
    response = match(client)
    assert response.status_code == expected, response.text
    assert len(requests) == 1
    assert KEY not in response.text + caplog.text


@pytest.mark.parametrize('kind', ['compressed', 'deeply_nested'])
def test_hostile_encoding_or_json_nesting_is_an_invalid_response(matcher_app, monkeypatch, kind):
    app, client = matcher_app
    ids = candidate(app)
    def respond(request):
        if kind == 'compressed':
            body = json.dumps({'choices': [{'message': {'content': json.dumps(decision(ids))}}]}).encode()
            return httpx.Response(200, stream=httpx.ByteStream(gzip.compress(body)),
                                  headers={'Content-Encoding': 'gzip'}, request=request)
        return httpx.Response(200, content=b'[' * 3000 + b']' * 3000, request=request)
    upstream(monkeypatch, handler=respond)
    response = match(client)
    assert response.status_code == 502, response.text
    assert response.json()['error']['code'] == 'template_matcher_invalid_response'


def test_sensitive_inputs_and_upstream_echo_never_leave_as_plaintext(matcher_app, monkeypatch):
    app, client = matcher_app
    ids = candidate(app, description='在岗 rtsp://user:password@localhost/video C:\\private\\clip.mp4',
        config={'default_target': 'person', 'default_rule': 'absence',
                'parameters': [], 'summary': 'password=camera-secret api_key=should-not-leave',
                'default_source': {'source_id': 'camera-secret'},
                'model_ref': {'model_id': '/private/model.onnx', 'model_version': '1',
                              'template_id': 'private-model', 'template_version': '1'}})
    requests = upstream(monkeypatch, decision(ids, reason='matched ' + KEY))
    response = match(client, '检查在岗 rtsp://alice:abc@127.0.0.1/live /private/video.mp4 videos/clip.mp4 api_key=other-secret 密码=local-secret')
    assert response.status_code == 200, response.text
    sent = requests[0].content.decode()
    for secret in ['rtsp://', 'password@', 'private', 'camera-secret', 'should-not-leave', 'other-secret', 'videos/clip.mp4', 'local-secret']:
        assert secret not in sent
    assert KEY not in response.text


def test_candidate_limit_reports_overflow_instead_of_silently_dropping(matcher_app, monkeypatch):
    app, client = matcher_app
    for _ in range(101):
        candidate(app)
    requests = upstream(monkeypatch, {})
    response = match(client)
    assert response.status_code == 422, response.text
    assert response.json()['error']['code'] == 'template_matcher_too_many_candidates'
    assert requests == []


@pytest.mark.parametrize('text', ['', '   ', 'x' * 2001])
def test_requirements_are_required_and_bounded(matcher_app, text):
    _, client = matcher_app
    assert match(client, text).status_code == 422


def test_environment_alias_and_custom_model_threshold(monkeypatch):
    from app.shared.config import Config
    monkeypatch.delenv('VISION_DEEPSEEK_API_KEY', raising=False)
    monkeypatch.setenv('DEEPSEEK_API_KEY', KEY)
    monkeypatch.setenv('VISION_DEEPSEEK_MODEL', 'deepseek-custom')
    monkeypatch.setenv('VISION_DEEPSEEK_MATCH_THRESHOLD', '.9')
    config = Config()
    assert config.deepseek_api_key.get_secret_value() == KEY
    assert config.deepseek_model == 'deepseek-custom'
    assert config.deepseek_match_threshold == .9
    assert KEY not in repr(config)
