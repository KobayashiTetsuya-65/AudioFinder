"""試聴（GET /api/audio/{id}）とエクスプローラーで開く（POST /api/reveal/{id}）。"""

import pytest
from fastapi.testclient import TestClient

from app import scanner, storage
from app.main import create_app

WAV = b"RIFF" + b"\x00" * 60  # 中身は見ないので、それらしいバイト列で足りる


@pytest.fixture
def env(tmp_path, data_dir):
    """登録フォルダ Pack（中に wav/mp3/ogg）と、その外にある secret.wav を用意して目録を書く。"""
    root = tmp_path / "Pack Folder"  # 空白を含むパス
    (root / "Battle").mkdir(parents=True)
    (root / "Battle" / "Boss.wav").write_bytes(WAV)
    (root / "Battle" / "Boss.mp3").write_bytes(b"ID3mp3")
    (root / "SE" / "日本語").mkdir(parents=True)
    (root / "SE" / "日本語" / "カード.ogg").write_bytes(b"OggSogg")
    (tmp_path / "secret.wav").write_bytes(b"secret")

    config = storage.load_config(data_dir)
    config["roots"] = [{"id": "r_1", "label": "Pack", "path": str(root), "enabled": True,
                        "added_at": "2026-10-06T21:00:00+09:00"}]
    storage.save_json(data_dir / "config.json", config)

    entries = [scanner.make_entry(config["roots"][0], rel, 30)
               for rel in ("Battle/Boss.wav", "Battle/Boss.mp3", "SE/日本語/カード.ogg")]
    # 目録が書き換えられて、登録フォルダの外を指している場合
    outside = {**entries[0], "id": "0123456789ab", "rel_path": "../secret.wav", "filename": "secret.wav"}
    index = {"version": 1, "scanned_at": "2026-10-06T21:30:00+09:00",
             "roots": [{"id": "r_1", "status": "ok", "file_count": 3}], "files": entries + [outside]}
    scanner.save_index(data_dir, index)

    revealed = []
    client = TestClient(create_app(data_dir, revealer=revealed.append))
    return {"client": client, "root": root, "ids": [e["id"] for e in entries], "outside_id": outside["id"],
            "revealed": revealed, "tmp": tmp_path}


# ---------- 試聴 ----------

@pytest.mark.parametrize("n, body, media_type", [
    (0, WAV, "audio/wav"),
    (1, b"ID3mp3", "audio/mpeg"),
    (2, b"OggSogg", "audio/ogg"),
])
def test_audio_returns_file(env, n, body, media_type):
    res = env["client"].get(f"/api/audio/{env['ids'][n]}")
    assert res.status_code == 200
    assert res.content == body
    assert res.headers["content-type"] == media_type


def test_audio_supports_range(env):
    """途中への頭出し（ブラウザの再生バーで飛ばす）ができる。"""
    res = env["client"].get(f"/api/audio/{env['ids'][0]}", headers={"Range": "bytes=0-3"})
    assert res.status_code == 206
    assert res.content == b"RIFF"


@pytest.mark.parametrize("bad_id", [
    "ffffffffffff",               # 形は正しいが目録にない
    "nothere",                    # 形が違う
    "..%2F..%2Fdata%2Fconfig.json",
    "..%5Csecret.wav",
    "%2E%2E",
])
def test_audio_unknown_id_is_404(env, bad_id):
    assert env["client"].get(f"/api/audio/{bad_id}").status_code == 404


def test_path_like_request_is_404(env):
    """IDの代わりにパスを渡しても、ファイルは返らない。"""
    for url in ("/api/audio/../secret.wav", "/api/audio/..\\secret.wav", "/api/audio/C:%5CWindows%5Cwin.ini"):
        res = env["client"].get(url)
        assert res.status_code == 404
        assert b"secret" not in res.content


def test_outside_of_root_is_refused(env):
    res = env["client"].get(f"/api/audio/{env['outside_id']}")
    assert res.status_code == 404
    assert b"secret" not in res.content
    assert env["client"].post(f"/api/reveal/{env['outside_id']}").status_code == 404
    assert env["revealed"] == []


def test_unregistered_root_is_refused(env, data_dir):
    """フォルダの登録を外したら、再スキャン前の目録に残っていても触らない。"""
    config = storage.load_config(data_dir)
    config["roots"] = []
    storage.save_json(data_dir / "config.json", config)
    assert env["client"].get(f"/api/audio/{env['ids'][0]}").status_code == 404
    assert env["client"].post(f"/api/reveal/{env['ids'][0]}").status_code == 404


def test_deleted_file_is_404(env):
    (env["root"] / "Battle" / "Boss.wav").unlink()
    assert env["client"].get(f"/api/audio/{env['ids'][0]}").status_code == 404


def test_no_index_yet_is_404(data_dir):
    client = TestClient(create_app(data_dir, revealer=lambda p: None))
    assert client.get("/api/audio/ffffffffffff").status_code == 404


# ---------- エクスプローラーで開く ----------

def test_reveal_opens_the_file(env):
    res = env["client"].post(f"/api/reveal/{env['ids'][2]}")
    assert res.status_code == 204
    assert env["revealed"] == [env["root"].resolve() / "SE" / "日本語" / "カード.ogg"]


def test_reveal_unknown_id_is_404(env):
    assert env["client"].post("/api/reveal/ffffffffffff").status_code == 404
    assert env["client"].post("/api/reveal/..%2F..%2Fsecret.wav").status_code == 404
    assert env["revealed"] == []


def test_reveal_is_post_only(env):
    assert env["client"].get(f"/api/reveal/{env['ids'][0]}").status_code in (404, 405)
    assert env["revealed"] == []
