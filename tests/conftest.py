import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def data_dir(tmp_path):
    """本物の data/ を汚さないよう、テストごとに空のフォルダを使う。"""
    return tmp_path / "data"


@pytest.fixture
def client(data_dir):
    return TestClient(create_app(data_dir))
