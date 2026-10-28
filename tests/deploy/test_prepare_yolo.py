import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def script():
    spec = importlib.util.spec_from_file_location('prepare_yolo', ROOT / 'deploy/scripts/prepare_yolo.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bad_source_digest_never_becomes_loadable_pt(tmp_path, monkeypatch):
    module = script()
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(b'untrusted pickle'))
    path = tmp_path / 'yolo11n.pt'
    with pytest.raises(ValueError, match='SHA256'):
        module.download_verified(module.OFFICIAL_SOURCE, path, '0'*64)
    assert not path.exists()


def test_nonofficial_source_rejected_before_network(tmp_path):
    with pytest.raises(ValueError, match='official'):
        script().download_verified('https://example.org/weights.pt', tmp_path / 'model.pt', '0'*64)


def test_trusted_source_reuses_verified_file_and_replaces_corruption(tmp_path, monkeypatch):
    import hashlib
    module = script()
    content = b'known trusted weight fixture'
    digest = hashlib.sha256(content).hexdigest()
    path = tmp_path / 'yolo11n.pt'
    path.write_bytes(b'corruption')
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(content))
    module.download_verified(module.OFFICIAL_SOURCE, path, digest)
    assert path.read_bytes() == content
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('should reuse verified file'))
    module.download_verified(module.OFFICIAL_SOURCE, path, digest)


def test_exporter_refuses_wrong_dependency_version_before_loading_checkpoint(tmp_path):
    metadata = tmp_path / 'ultralytics-99.0.0.dist-info'
    metadata.mkdir()
    (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: ultralytics\nVersion: 99.0.0\n')
    environment = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = subprocess.run([sys.executable, '-c', script().EXPORT_CODE, 'must-never-be-loaded.pt',
                             json.dumps({'ultralytics': '8.3.230'})],
                            env=environment, capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Exporter version mismatch for ultralytics' in result.stderr
