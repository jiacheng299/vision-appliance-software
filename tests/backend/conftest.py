import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

@pytest.fixture
def app(tmp_path):
    try:
        from app.main import create_app
    except ImportError:
        pytest.fail('Foundation API application has not been implemented')
    return create_app(var_root=tmp_path, testing=True)

@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client
