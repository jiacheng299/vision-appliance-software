import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.agents.schemas import CapabilityRef
from app.modules.models.schemas import ModelInput
from app.shared.config import Config, ROOT
from app.shared.db import make_engine, migrate, session_factory
from app.shared.errors import Error


@pytest.fixture
def prepared(tmp_path):
    config = Config(var_root=tmp_path, _env_file=None)
    config.prepare()
    engine = make_engine(config)
    migrate(engine)
    sessions = session_factory(engine)
    folder = tmp_path / 'models/yolo11n'
    folder.mkdir(parents=True)
    model = folder / 'yolo11n.onnx'
    model.write_bytes(b'controlled-inert-model-test-fixture')
    source = ROOT / 'deploy/yolo-model.json'
    manifest = json.loads(source.read_text(encoding='utf-8')) | {
        'format': 'onnx', 'model_path': str(model.resolve()),
        'sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
        'source_manifest_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'input_shape': [1, 3, 640, 640], 'output_shape': [1, 84, 8400]}
    (folder / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    yield config, sessions, model, manifest
    engine.dispose()


def implementation():
    try:
        return importlib.import_module('app.modules.models.yolo_services')
    except ModuleNotFoundError:
        pytest.fail('Trusted YOLO model service is not implemented')


def definition(version):
    return ModelInput(name='YOLO11n COCO 人员检测', version=version,
        runtime_type='yolo11n-onnx-person', file_id='uploaded', template={
            'name': '人员缺岗规则', 'version': version, 'targets': ['person'], 'rules': ['absence'],
            'requires_region': ['absence'], 'requires_duration': ['absence'],
            'defaults': {'duration_seconds': 30}, 'parameter_keys': ['target', 'rule', 'duration_seconds',
                'confidence_threshold', 'min_count', 'alarm_interval_seconds', 'sample_interval_seconds']})


def adapter(prepared, monkeypatch, *, self_test_error=False):
    module = implementation()
    config, sessions, _, _ = prepared
    monkeypatch.setattr(module, 'dependencies_ready', lambda: True)
    monkeypatch.setattr(module, 'black_frame', lambda: SimpleNamespace(shape=(640, 640, 3)))
    class Detector:
        def __init__(self, path, confidence=.5):
            self.path = path
        def detect(self, frame):
            assert frame.shape == (640, 640, 3)
            if self_test_error:
                raise RuntimeError('Unusable ONNX graph')
            return []
    monkeypatch.setattr(module, 'YoloPersonDetector', Detector)
    return module.YoloModelServices(config, sessions)


def test_readiness_requires_installed_artifact_and_dependencies(prepared, monkeypatch):
    service = adapter(prepared, monkeypatch)
    assert service.is_ready() is True
    monkeypatch.setattr(implementation(), 'dependencies_ready', lambda: False)
    assert service.is_ready() is False


def test_readiness_rejects_unloadable_native_dependencies(prepared, monkeypatch):
    module = implementation()
    service = module.YoloModelServices(prepared[0], prepared[1])
    monkeypatch.setattr(module.importlib.util, 'find_spec', lambda name: object())
    def broken_import(name):
        raise ImportError('native extension DLL unavailable')
    monkeypatch.setattr(module.importlib, 'import_module', broken_import)
    assert service.is_ready() is False


@pytest.mark.parametrize('damage', ['missing', 'hash', 'path', 'source', 'shape', 'structure'])
def test_untrusted_manifest_never_becomes_ready(prepared, monkeypatch, damage):
    config, _, model, manifest = prepared
    if damage == 'missing':
        model.unlink()
    elif damage == 'hash':
        model.write_bytes(b'corrupted')
    elif damage == 'structure':
        (model.parent / 'manifest.json').write_text('[]', encoding='utf-8')
    else:
        field, value = {'path': ('model_path', str(config.var_root.parent / 'escaped.onnx')),
                        'source': ('source_sha256', '0' * 64), 'shape': ('output_shape', [1, 6, 8400])}[damage]
        manifest[field] = value
        (model.parent / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    assert adapter(prepared, monkeypatch).is_ready() is False


def test_verified_copy_runs_self_test_before_passing(prepared, monkeypatch):
    _, _, model, manifest = prepared
    service = adapter(prepared, monkeypatch)
    state, _ = service.verify(definition(manifest['model_version']), model, manifest['sha256'])
    assert state == 'passed'
    assert adapter(prepared, monkeypatch, self_test_error=True).verify(
        definition(manifest['model_version']), model, manifest['sha256'])[0] == 'failed'


@pytest.mark.parametrize('change', ['runtime', 'target', 'rule', 'region', 'duration', 'parameter', 'defaults', 'version'])
def test_unsupported_capability_claims_are_not_verified(prepared, monkeypatch, change):
    _, _, model, manifest = prepared
    body = definition(manifest['model_version'])
    if change == 'runtime': body.runtime_type = 'arbitrary-python'
    elif change == 'target': body.template.targets = ['person', 'fire']
    elif change == 'rule': body.template.rules = ['intrusion']
    elif change == 'region': body.template.requires_region = []
    elif change == 'duration': body.template.requires_duration = []
    elif change == 'parameter': body.template.parameter_keys.append('color')
    elif change == 'defaults': body.template.defaults['color'] = 'red'
    elif change == 'version': body.version = 'invented-version'
    assert adapter(prepared, monkeypatch).verify(body, model, manifest['sha256'])[0] == 'failed'


def test_arbitrary_upload_is_not_verified_by_filename(prepared, monkeypatch):
    config, _, _, manifest = prepared
    path = config.var_root / 'model-files/yolo11n.onnx'
    path.parent.mkdir()
    path.write_bytes(b'arbitrary ONNX')
    service = adapter(prepared, monkeypatch)
    assert service.verify(definition(manifest['model_version']), path,
                          hashlib.sha256(path.read_bytes()).hexdigest())[0] == 'failed'


def registered(prepared):
    from app.modules.models.models import ModelFile, ModelPair
    config, sessions, model, manifest = prepared
    folder = config.var_root / 'model-files'
    folder.mkdir(exist_ok=True)
    uploaded = folder / 'uploaded'
    uploaded.write_bytes(model.read_bytes())
    ref = CapabilityRef(model_id='person-model', model_version=manifest['model_version'],
                        template_id='person-rules', template_version=manifest['model_version'])
    with sessions() as db:
        db.add(ModelFile(id='uploaded', filename='yolo11n.onnx', size_bytes=uploaded.stat().st_size,
                         checksum=manifest['sha256']))
        db.flush()
        db.add(ModelPair(model_id=ref.model_id, version=ref.model_version, template_id=ref.template_id,
            template_version=ref.template_version, file_id='uploaded',
            definition=definition(manifest['model_version']).model_dump(mode='json'),
            validation='passed', status='available', data_origin='real'))
        db.commit()
    return ref, uploaded


def test_resolve_model_returns_the_verified_controlled_copy(prepared, monkeypatch):
    ref, uploaded = registered(prepared)
    assert adapter(prepared, monkeypatch).resolve_model(ref) == uploaded.resolve()


@pytest.mark.parametrize('damage', ['archive', 'pending', 'mock', 'reference', 'hash', 'size', 'escape'])
def test_resolve_model_rechecks_registry_and_file_integrity(prepared, monkeypatch, damage):
    from app.modules.models.models import ModelFile, ModelPair
    _, sessions, _, _ = prepared
    ref, uploaded = registered(prepared)
    with sessions() as db:
        row = db.get(ModelPair, (ref.model_id, ref.model_version))
        if damage == 'archive': row.status = 'archived'
        elif damage == 'pending': row.validation = 'pending'
        elif damage == 'mock': row.data_origin = 'mock'
        elif damage == 'reference': ref.template_version = 'other'
        elif damage == 'hash': uploaded.write_bytes(b'bad bytes')
        elif damage == 'size': db.get(ModelFile, 'uploaded').size_bytes += 1
        elif damage == 'escape':
            escaped = uploaded.parent.parent / 'escaped.onnx'
            escaped.write_bytes(uploaded.read_bytes())
            existing = db.get(ModelFile, 'uploaded')
            db.add(ModelFile(id='../escaped.onnx', filename='escaped.onnx', size_bytes=existing.size_bytes,
                             checksum=existing.checksum))
            db.flush()
            row.file_id = '../escaped.onnx'
        db.commit()
    with pytest.raises(Error):
        adapter(prepared, monkeypatch).resolve_model(ref)
