import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def script():
    path = ROOT / 'deploy/scripts/setup_presence.py'
    assert path.is_file(), 'Public API presence registration script is not implemented'
    spec = importlib.util.spec_from_file_location('setup_presence', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intrusion_script():
    path = ROOT / 'deploy/scripts/setup_intrusion.py'
    assert path.is_file(), 'Public API intrusion registration script is not implemented'
    spec = importlib.util.spec_from_file_location('setup_intrusion', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def artifact(tmp_path):
    source = tmp_path / 'deploy/yolo-model.json'
    source.parent.mkdir()
    source.write_bytes((ROOT / 'deploy/yolo-model.json').read_bytes())
    folder = tmp_path / 'var/models/yolo11n'
    folder.mkdir(parents=True)
    model = folder / 'yolo11n.onnx'
    model.write_bytes(b'controlled ONNX registration fixture')
    manifest = json.loads(source.read_text(encoding='utf-8')) | {'format': 'onnx',
        'model_path': str(model.resolve()), 'sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
        'source_manifest_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'input_shape': [1, 3, 640, 640], 'output_shape': [1, 84, 8400]}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return tmp_path, model, manifest


class API:
    def __init__(self, manifest, model):
        self.manifest, self.model = manifest, model
        self.models, self.templates, self.calls, self.keys = [], [], [], []
        self.lose_once = None
        self.verification = 'passed'

    def __call__(self, request):
        path = request.url.path.removeprefix('/api/v1/')
        self.calls.append((request.method, path))
        body = json.loads(request.content) if request.content and path != 'model-files' else None
        if request.method == 'GET':
            if path == 'models': result = {'items': self.models, 'next_cursor': None}
            elif path == 'agent-templates': result = {'items': self.templates, 'next_cursor': None}
            elif path.startswith('agent-templates/'):
                result = next(row for row in self.templates if row['id'] == path.split('/')[1])
            else: raise AssertionError(f'Unexpected read {path}')
        elif path == 'model-files':
            assert request.content == self.model.read_bytes()
            result = {'id': 'upload1', 'filename': 'yolo11n.onnx', 'checksum': self.manifest['sha256'],
                      'size_bytes': self.model.stat().st_size}
        elif path == 'models':
            self.keys.append(request.headers['Idempotency-Key'])
            result = body | {'id': 'model1', 'template_id': 'capability1', 'validation': 'pending',
                'checksum': self.manifest['sha256'], 'size_bytes': self.model.stat().st_size,
                'row_version': 1, 'status': 'available', 'data_origin': 'real'}
            self.models.append(result)
        elif path.endswith('/verify'):
            result = self.models[0]
            assert body == {'row_version': result['row_version']}
            result.update(validation=self.verification, row_version=result['row_version'] + 1)
        elif path == 'agent-templates':
            self.keys.append(request.headers['Idempotency-Key'])
            if body['config'].get('default_source'):
                body['config']['default_source'].update(start_media_ms=None, end_media_ms=None)
            revision = {'id': 'revision1', 'config': body['config'], 'state': 'draft'}
            result = body | {'id': 'template1', 'row_version': 1, 'archived_at': None,
                             'latest_revision': revision, 'published_revision': None}
            self.templates.append(result)
        elif path.endswith('/publish'):
            self.keys.append(request.headers['Idempotency-Key'])
            result = self.templates[0]
            assert body == {'row_version': result['row_version'], 'revision_id': 'revision1'}
            result.update(published_revision=result['latest_revision'], row_version=result['row_version'] + 1)
            result['latest_revision']['state'] = 'published'
        else:
            raise AssertionError(f'Unexpected mutation {path}')
        if path == self.lose_once:
            self.lose_once = None
            raise httpx.ReadTimeout('Response lost after API committed', request=request)
        return httpx.Response(201 if path in ('models', 'model-files', 'agent-templates') and request.method == 'POST' else 200,
                              json=result, request=request)


def client(api):
    return httpx.Client(transport=httpx.MockTransport(api), base_url='http://127.0.0.1:8000/api/v1/')


def test_register_uses_public_upload_verify_and_publish_contracts_idempotently(artifact):
    root, model, manifest = artifact
    api = API(manifest, model)
    module = script()
    with client(api) as http:
        first = module.register(http, root=root)
        second = module.register(http, root=root)
    assert first == second
    assert len(api.models) == len(api.templates) == 1
    assert api.calls.count(('POST', 'model-files')) == 1
    assert ('POST', 'models/model1/versions/' + manifest['model_version'] + '/verify') in api.calls
    assert ('POST', 'agent-templates/template1/publish') in api.calls
    parameters = {p['key']: p['value'] for p in api.templates[0]['latest_revision']['config']['parameters']}
    assert parameters == {'duration_seconds': 30, 'confidence_threshold': .5, 'min_count': 1,
                          'alarm_interval_seconds': 60, 'sample_interval_seconds': 1}
    assert set(parameters) <= set(api.models[0]['template']['parameter_keys'])
    assert api.models[0]['runtime_type'] == 'yolo11n-onnx-person'
    assert api.templates[0]['latest_revision']['config'].get('default_source') is None
    assert json.loads((model.parent / 'registration.json').read_text(encoding='utf-8')) == first


def test_register_intrusion_uses_fixed_timing_and_publishes_idempotently(artifact):
    root, model, manifest = artifact
    api = API(manifest,model)
    module = intrusion_script()
    with client(api) as http:
        first = module.register(http,root=root)
        second = module.register(http,root=root)
    assert first == second
    assert len(api.models) == len(api.templates) == 1
    assert api.models[0]['template']['rules'] == ['intrusion']
    parameters = {item['key']:item['value'] for item in api.templates[0]['latest_revision']['config']['parameters']}
    assert parameters == {'duration_seconds':8,'confidence_threshold':.5,'tracking_timeout_seconds':5,
                          'exit_confirmation_seconds':10,'sample_interval_seconds':1}
    assert api.templates[0]['name'] == '人员区域入侵监测'
    assert json.loads((model.parent / 'intrusion-registration.json').read_text(encoding='utf-8')) == first


@pytest.mark.parametrize('stage', ['models', 'agent-templates', 'agent-templates/template1/publish'])
def test_lost_http_response_recovers_without_duplicate_models_or_templates(artifact, stage):
    root, model, manifest = artifact
    api = API(manifest, model)
    api.lose_once = stage
    module = script()
    with client(api) as http:
        with pytest.raises(httpx.ReadTimeout): module.register(http, root=root)
        result = module.register(http, root=root)
    assert result['template_revision_id'] == 'revision1'
    assert len(api.models) == len(api.templates) == 1
    assert len(set(api.keys)) == len(api.keys)


def test_optional_video_uses_a_whole_frame_region(artifact):
    root, model, manifest = artifact
    api = API(manifest, model)
    with client(api) as http:
        script().register(http, root=root, source_id='video1')
    source = api.templates[0]['latest_revision']['config']['default_source']
    assert source['source_id'] == 'video1'
    assert source['regions'][0]['points'] == [[0, 0], [1, 0], [1, 1], [0, 1]]


@pytest.mark.parametrize('with_source', [False, True])
def test_registration_against_actual_api_dtos(artifact, monkeypatch, with_source):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / 'backend'))
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.modules.models import yolo_services
    root, _, _ = artifact
    monkeypatch.setenv('VISION_AGENT_DEMO', 'false')
    monkeypatch.setattr(yolo_services, 'dependencies_ready', lambda: True)
    monkeypatch.setattr(yolo_services, 'black_frame', lambda: SimpleNamespace(shape=(640, 640, 3)))
    class Detector:
        def __init__(self, *args, **kwargs): pass
        def detect(self, frame): return []
    monkeypatch.setattr(yolo_services, 'YoloPersonDetector', Detector)
    app = create_app(var_root=root / 'var', testing=True)
    model_service = yolo_services.YoloModelServices(app.state.config, app.state.sessions)
    app.state.model_services = model_service
    app.state.agent_services.model_adapter = model_service
    with TestClient(app, base_url='http://testserver/api/v1/') as http:
        source_id = http.post('sources', json={'kind': 'camera', 'name': '默认输入',
            'address': 'rtsp://127.0.0.1/local-test'}).json()['id'] if with_source else None
        module = script()
        first = module.register(http, root=root, source_id=source_id)
        assert module.register(http, root=root, source_id=source_id) == first
        assert len(http.get('models').json()['items']) == 1
        assert len(http.get('agent-templates').json()['items']) == 1


def test_intrusion_registration_against_actual_api_dtos(artifact, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / 'backend'))
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.modules.models import yolo_services
    root, _, _ = artifact
    monkeypatch.setenv('VISION_AGENT_DEMO', 'false')
    monkeypatch.setattr(yolo_services, 'dependencies_ready', lambda: True)
    monkeypatch.setattr(yolo_services, 'black_frame', lambda: SimpleNamespace(shape=(640, 640, 3)))
    class Detector:
        def __init__(self, *args, **kwargs): pass
        def detect(self, frame): return []
    monkeypatch.setattr(yolo_services, 'YoloPersonDetector', Detector)
    app = create_app(var_root=root / 'var', testing=True)
    model_service = yolo_services.YoloModelServices(app.state.config, app.state.sessions)
    app.state.model_services = model_service
    app.state.agent_services.model_adapter = model_service
    with TestClient(app, base_url='http://testserver/api/v1/') as http:
        module = intrusion_script()
        first = module.register(http,root=root)
        assert module.register(http,root=root) == first
        models = http.get('models').json()['items']
        templates = http.get('agent-templates').json()['items']
        assert len(models) == len(templates) == 1
        assert models[0]['template']['rules'] == ['intrusion']
        assert templates[0]['name'] == '人员区域入侵监测'


def test_presence_and_intrusion_share_one_trusted_file_but_keep_separate_capabilities(artifact, monkeypatch):
    import sys
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / 'backend'))
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.modules.models import yolo_services
    root, _, _ = artifact
    monkeypatch.setenv('VISION_AGENT_DEMO', 'false')
    monkeypatch.setattr(yolo_services, 'dependencies_ready', lambda: True)
    monkeypatch.setattr(yolo_services, 'black_frame', lambda: SimpleNamespace(shape=(640, 640, 3)))
    class Detector:
        def __init__(self, *args, **kwargs): pass
        def detect(self, frame): return []
    monkeypatch.setattr(yolo_services, 'YoloPersonDetector', Detector)
    app = create_app(var_root=root / 'var', testing=True)
    model_service = yolo_services.YoloModelServices(app.state.config, app.state.sessions)
    app.state.model_services = model_service
    app.state.agent_services.model_adapter = model_service
    with TestClient(app, base_url='http://testserver/api/v1/') as http:
        presence = script().register(http,root=root)
        intrusion = intrusion_script().register(http,root=root)
        assert presence['file_id'] == intrusion['file_id']
        models = http.get('models').json()['items']
        templates = http.get('agent-templates').json()['items']
        assert len(models) == len(templates) == 2
        assert {item['template']['rules'][0] for item in models} == {'absence','intrusion'}
        assert {item['name'] for item in templates} == {'人员在岗监测','人员区域入侵监测'}
        assert len(list((root / 'var/model-files').iterdir())) == 1


def test_user_template_changes_are_preserved_without_new_template(artifact):
    root, model, manifest = artifact
    api = API(manifest, model)
    module = script()
    with client(api) as http:
        module.register(http, root=root)
        api.templates[0]['name'] = '用户已改名'
        api.templates[0]['latest_revision']['config']['parameters'][0]['value'] = 120
        count = len(api.calls)
        with pytest.raises(RuntimeError, match='修改|changed'):
            module.register(http, root=root)
    assert all(method == 'GET' for method, _ in api.calls[count:])
    assert len(api.templates) == 1
    assert api.templates[0]['latest_revision']['config']['parameters'][0]['value'] == 120


def test_failed_real_model_verification_never_publishes_template(artifact):
    root, model, manifest = artifact
    api = API(manifest, model)
    api.verification = 'failed'
    with client(api) as http, pytest.raises(RuntimeError, match='校验|verification'):
        script().register(http, root=root)
    assert api.templates == []


@pytest.mark.parametrize('damage', ['hash', 'source', 'path', 'shape', 'structure'])
def test_invalid_artifact_never_uploads_or_registers(artifact, damage):
    root, model, manifest = artifact
    if damage == 'hash': model.write_bytes(b'corrupt')
    elif damage == 'structure':
        (model.parent / 'manifest.json').write_text('[]', encoding='utf-8')
    else:
        field, value = {'source': ('source_sha256', '0' * 64), 'path': ('model_path', '/outside.onnx'),
                        'shape': ('input_shape', [1, 3, 320, 320])}[damage]
        manifest[field] = value
        (model.parent / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    api = API(manifest, model)
    with client(api) as http, pytest.raises((RuntimeError, ValueError)):
        script().register(http, root=root)
    assert api.calls == []
