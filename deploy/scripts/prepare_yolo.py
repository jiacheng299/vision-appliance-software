"""Prepare the pinned official YOLO11n ONNX; never accepts user PT/pickle files.

Run with Python 3.13: python deploy/scripts/prepare_yolo.py
Outputs var/models/yolo11n/yolo11n.onnx and manifest.json for API registration.
Exporter dependencies live in var/tools/yolo-export, outside the application venv.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import venv

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_SOURCE = 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt'
EXPORT_CODE = '''
import importlib.metadata
import json
import sys
pins = json.loads(sys.argv[2])
for package in ('ultralytics', 'torch', 'torchvision', 'onnx'):
    actual = importlib.metadata.version(package).split('+')[0]
    if actual != pins[package]:
        raise RuntimeError(f'Exporter version mismatch for {package}: {actual}')
from ultralytics import YOLO
p = YOLO(sys.argv[1]).export(format='onnx', imgsz=640, opset=17,
    dynamic=False, simplify=False, nms=False, device='cpu', half=False)
import onnx
onnx.checker.check_model(p)
'''


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download_verified(url: str, path: Path, digest: str) -> None:
    if url != OFFICIAL_SOURCE:
        raise ValueError('Only the pinned official Ultralytics source is allowed')
    if path.is_file() and sha256(path) == digest:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.download')
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output)
        if sha256(temporary) != digest:
            raise ValueError('Official source SHA256 mismatch; export refused')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(*, install: bool = True) -> dict:
    config_path = ROOT / 'deploy/yolo-model.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    output_dir = ROOT / 'var/models/yolo11n'
    output_dir.mkdir(parents=True, exist_ok=True)
    weights = output_dir / 'yolo11n.pt'
    download_verified(config['source_url'], weights, config['source_sha256'])
    environment = ROOT / 'var/tools/yolo-export'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    versions = config['export']
    if install:
        subprocess.run([str(python), '-m', 'pip', 'install', '--no-cache-dir', '--no-deps', '--index-url',
                        'https://download.pytorch.org/whl/cpu', f"torch=={versions['torch']}",
                        f"torchvision=={versions['torchvision']}"], check=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--no-cache-dir', '--index-url',
                        'https://pypi.org/simple', f"ultralytics=={versions['ultralytics']}",
                        f"onnx=={versions['onnx']}", 'numpy==2.2.6', 'opencv-python==4.12.0.88'], check=True)
    # Only the verified fixed official checkpoint reaches PyTorch deserialization.
    export_env = dict(os.environ, YOLO_AUTOINSTALL='false', YOLO_CONFIG_DIR=str(environment / 'settings'))
    subprocess.run([str(python), '-c', EXPORT_CODE, str(weights), json.dumps(versions)],
                   check=True, env=export_env, cwd=output_dir)
    model = output_dir / 'yolo11n.onnx'
    if not model.is_file():
        raise RuntimeError('YOLO export did not produce an ONNX model')
    manifest = dict(config, format='onnx', model_path=str(model.resolve()),
                    sha256=sha256(model), source_manifest_sha256=sha256(config_path),
                    input_shape=[1, 3, 640, 640], output_shape=[1, 84, 8400])
    manifest_path = output_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return dict(manifest, manifest_path=str(manifest_path.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-install', action='store_true', help='Reuse an already provisioned isolated exporter')
    args = parser.parse_args()
    print(json.dumps(prepare(install=not args.skip_install), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
