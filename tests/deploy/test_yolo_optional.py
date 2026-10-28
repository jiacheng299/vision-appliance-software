import subprocess
import sys
from pathlib import Path


def test_detector_module_imports_without_optional_vision_dependencies():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-c', '''
import builtins
original = builtins.__import__
def restricted(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'onnxruntime', 'cv2', 'torch', 'ultralytics'}:
        raise ImportError('optional dependency unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = restricted
from app.modules.models.yolo import YoloPersonDetector
try:
    YoloPersonDetector(__import__('pathlib').Path('missing.onnx'))
except FileNotFoundError:
    pass
'''], cwd=root / 'backend', capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_starting_detector_without_optional_dependencies_reports_installation(tmp_path):
    root = Path(__file__).resolve().parents[2]
    model = tmp_path / 'model.onnx'
    model.write_bytes(b'placeholder')
    result = subprocess.run([sys.executable, '-c', '''
import builtins, sys
from pathlib import Path
original = builtins.__import__
def restricted(name, *args, **kwargs):
    if name.split('.')[0] in {'numpy', 'onnxruntime', 'cv2'}:
        raise ImportError('optional dependency unavailable')
    return original(name, *args, **kwargs)
builtins.__import__ = restricted
from app.modules.models.yolo import YoloPersonDetector
try:
    YoloPersonDetector(Path(sys.argv[1]))
except RuntimeError as exc:
    assert 'requirements-vision.txt' in str(exc)
else:
    raise AssertionError('missing dependencies were silently accepted')
''', str(model)], cwd=root / 'backend', capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
