from app import storage
from app.main import create_app


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_index_page_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "AUDIO FINDER" in res.text
    for label in ("探す", "履歴", "設定"):
        assert label in res.text


def test_config_is_created_with_defaults(client, data_dir):
    path = data_dir / "config.json"
    assert path.exists()
    assert storage.load_json(path) == storage.DEFAULT_CONFIG


def test_existing_config_is_not_overwritten(data_dir):
    custom = {**storage.DEFAULT_CONFIG, "server": {"host": "127.0.0.1", "port": 9999}}
    storage.save_json(data_dir / "config.json", custom)
    create_app(data_dir)
    assert storage.load_json(data_dir / "config.json")["server"]["port"] == 9999


def test_save_json_leaves_no_temp_file(data_dir):
    storage.save_json(data_dir / "x.json", {"a": 1})
    assert [p.name for p in data_dir.iterdir()] == ["x.json"]
