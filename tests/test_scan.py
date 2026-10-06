import json
import time
import wave

import pytest

from app import scanner, storage

THRESHOLD = 30


def make_wav(path, seconds, rate=8000):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(rate)
        w.writeframes(b"\x80" * int(rate * seconds))


def make_config(*roots):
    config = json.loads(json.dumps(storage.DEFAULT_CONFIG))
    config["roots"] = [
        {"id": rid, "label": label, "path": str(path), "enabled": enabled, "added_at": "2026-10-06T21:00:00+09:00"}
        for rid, label, path, enabled in roots
    ]
    return config


# ---------- 単語への分解 ----------

@pytest.mark.parametrize("texts, expected", [
    (("Fantasy RPG Music Pack", "Battle/Boss_Theme_Loop"), "fantasy rpg music pack battle boss theme loop"),
    (("Pack", "SE/UI/CardDraw01"), "pack se ui card draw 01"),
    (("Pack", "RPGMusic/BGM-02 final.v2"), "pack rpg music bgm 02 final v 2"),
    (("効果音", "ボス戦BGM_01"), "効果音 ボス戦 bgm 01"),
    # 全角の空白・数字・英字、日本語の記号も区切りとして扱う
    (("BGM", "Giga_Boss　戦闘１"), "bgm giga boss 戦闘 1"),
    (("BGM", "【ＳＥ】カード・ドロー（短）"), "bgm se カード ドロー 短"),
])
def test_to_words(texts, expected):
    assert scanner.to_words(*texts) == expected


# ---------- ID ----------

def test_file_id_is_stable_and_12_hex():
    a = scanner.file_id("r_7f3a", "Battle/Boss.ogg")
    assert a == scanner.file_id("r_7f3a", "Battle/Boss.ogg")
    assert len(a) == 12 and int(a, 16) >= 0
    assert a != scanner.file_id("r_7f3a", "Battle/Boss2.ogg")
    assert a != scanner.file_id("r_0000", "Battle/Boss.ogg")


def test_same_file_keeps_id_after_rescan(tmp_path):
    make_wav(tmp_path / "pack" / "a" / "x.wav", 0.5)
    config = make_config(("r_1", "Pack", tmp_path / "pack", True))
    first = scanner.scan(config)["files"][0]["id"]
    make_wav(tmp_path / "pack" / "b.wav", 0.5)  # 他のファイルが増えても変わらない
    second = [f["id"] for f in scanner.scan(config)["files"] if f["rel_path"] == "a/x.wav"]
    assert second == [first]


# ---------- likely_bgm ----------

@pytest.mark.parametrize("duration, expected", [
    (29.9, False), (30.0, True), (30.1, True), (0.6, False), (None, None),
])
def test_likely_bgm(duration, expected):
    assert scanner.likely_bgm(duration, THRESHOLD) is expected


def test_likely_bgm_from_real_files(tmp_path):
    make_wav(tmp_path / "pack" / "short.wav", 29.9)
    make_wav(tmp_path / "pack" / "just.wav", 30)
    (tmp_path / "pack" / "broken.mp3").write_bytes(b"this is not audio")
    files = {f["filename"]: f for f in scanner.scan(make_config(("r_1", "Pack", tmp_path / "pack", True)))["files"]}
    assert (files["short.wav"]["duration_sec"], files["short.wav"]["likely_bgm"]) == (29.9, False)
    assert (files["just.wav"]["duration_sec"], files["just.wav"]["likely_bgm"]) == (30.0, True)
    assert files["broken.mp3"]["duration_sec"] is None
    assert files["broken.mp3"]["likely_bgm"] is None
    assert files["broken.mp3"]["readable"] is False
    assert files["short.wav"]["readable"] is True


# ---------- 目録の中身 ----------

def test_entry_fields(tmp_path):
    make_wav(tmp_path / "pack" / "SE" / "UI" / "CardDraw01.WAV", 0.6)
    make_wav(tmp_path / "pack" / "Top.wav", 1)
    (tmp_path / "pack" / "readme.txt").write_text("x")
    (tmp_path / "pack" / "cover.flac").write_bytes(b"x")
    index = scanner.scan(make_config(("r_1", "My Pack", tmp_path / "pack", True)))

    assert [f["rel_path"] for f in index["files"]] == ["Top.wav", "SE/UI/CardDraw01.WAV"]
    f = index["files"][1]
    assert set(f) == {"id", "root_id", "rel_path", "filename", "folder", "ext", "duration_sec", "likely_bgm",
                      "size_bytes", "mtime", "readable", "words"}
    assert f["id"] == scanner.file_id("r_1", "SE/UI/CardDraw01.WAV")
    assert f["root_id"] == "r_1"
    assert f["filename"] == "CardDraw01.WAV"
    assert f["folder"] == "SE/UI"
    assert f["ext"] == "wav"
    assert f["duration_sec"] == 0.6
    assert f["size_bytes"] == (tmp_path / "pack" / "SE" / "UI" / "CardDraw01.WAV").stat().st_size
    assert f["mtime"].endswith("+09:00")
    assert f["words"] == "my pack se ui card draw 01"
    assert index["files"][0]["folder"] == ""
    assert index["roots"] == [{"id": "r_1", "status": "ok", "file_count": 2}]
    assert index["version"] == 1
    assert index["scanned_at"].endswith("+09:00")


def test_all_three_formats_are_included(tmp_path):
    for name in ("a.wav", "b.mp3", "c.ogg", "d.OGG"):
        (tmp_path / "pack").mkdir(exist_ok=True)
        (tmp_path / "pack" / name).write_bytes(b"x")
    files = scanner.scan(make_config(("r_1", "P", tmp_path / "pack", True)))["files"]
    assert [f["ext"] for f in files] == ["wav", "mp3", "ogg", "ogg"]


# ---------- missing の扱い ----------

def test_missing_root_is_skipped(tmp_path):
    make_wav(tmp_path / "ok" / "a.wav", 0.5)
    (tmp_path / "is_a_file").write_text("x")
    config = make_config(
        ("r_miss", "External", tmp_path / "not_here", True),
        ("r_file", "File", tmp_path / "is_a_file", True),
        ("r_ok", "Ok", tmp_path / "ok", True),
    )
    index = scanner.scan(config)
    assert index["roots"] == [
        {"id": "r_miss", "status": "missing", "file_count": 0},
        {"id": "r_file", "status": "missing", "file_count": 0},
        {"id": "r_ok", "status": "ok", "file_count": 1},
    ]
    assert [f["root_id"] for f in index["files"]] == ["r_ok"]


def test_disabled_root_is_not_scanned(tmp_path):
    make_wav(tmp_path / "off" / "a.wav", 0.5)
    index = scanner.scan(make_config(("r_off", "Off", tmp_path / "off", False)))
    assert index["roots"] == []
    assert index["files"] == []


def test_progress_is_reported(tmp_path):
    for i in range(3):
        make_wav(tmp_path / "pack" / f"{i}.wav", 0.1)
    calls = []
    scanner.scan(make_config(("r_1", "P", tmp_path / "pack", True)), lambda d, t: calls.append((d, t)))
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]


# ---------- 1件1行の出力 ----------

def test_index_json_has_one_file_per_line(tmp_path):
    make_wav(tmp_path / "pack" / "Battle" / "Boss_Theme_Loop.wav", 0.5)
    make_wav(tmp_path / "pack" / "SE" / "CardDraw01.wav", 0.5)
    data_dir = tmp_path / "data"
    index = scanner.scan(make_config(("r_1", "ボス Pack", tmp_path / "pack", True)))
    scanner.save_index(data_dir, index)

    text = (data_dir / "index.json").read_text(encoding="utf-8")
    assert json.loads(text) == index  # JSONとして正しい
    assert scanner.load_index(data_dir) == index
    assert "ボス" in text  # \uXXXX にしない（日本語のまま検索できる）

    lines = text.splitlines()
    for f in index["files"]:
        hits = [line for line in lines if f'"id":"{f["id"]}"' in line]
        assert len(hits) == 1
        assert json.loads(hits[0].rstrip(",")) == f  # 当たった1行だけで情報がそろう

    # 「boss」「card draw」の文字列検索で当たる
    assert [line for line in lines if "boss" in line and "Boss_Theme_Loop" in line]
    assert [line for line in lines if "card draw" in line and "CardDraw01" in line]
    assert not list(data_dir.glob("*.tmp"))


def test_empty_index_is_valid_json(tmp_path):
    scanner.save_index(tmp_path, scanner.scan(make_config()))
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))["files"] == []


# ---------- API ----------

def wait_scan(client, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get("/api/scan").json()
        if not s["running"]:
            return s
        time.sleep(0.05)
    raise AssertionError("スキャンが終わらない")


def test_scan_status_before_first_scan(client):
    assert client.get("/api/scan").json() == {"running": False, "done": 0, "total": 0, "error": None, "index": None}


def test_scan_api(client, data_dir, tmp_path):
    make_wav(tmp_path / "pack" / "a.wav", 0.5)
    make_wav(tmp_path / "pack" / "b.wav", 0.5)
    client.post("/api/roots", json={"path": str(tmp_path / "pack"), "label": "Pack"})
    client.post("/api/roots", json={"path": str(tmp_path / "gone"), "label": "Gone"})

    assert client.post("/api/scan").status_code == 202
    s = wait_scan(client)
    assert s["error"] is None
    assert (s["done"], s["total"]) == (2, 2)
    assert s["index"]["file_count"] == 2
    assert [r["status"] for r in s["index"]["roots"]] == ["ok", "missing"]
    assert len(scanner.load_index(data_dir)["files"]) == 2


def test_scan_summary_survives_restart(data_dir, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    make_wav(tmp_path / "pack" / "a.wav", 0.5)
    client = TestClient(create_app(data_dir))
    client.post("/api/roots", json={"path": str(tmp_path / "pack")})
    client.post("/api/scan")
    scanned_at = wait_scan(client)["index"]["scanned_at"]

    again = TestClient(create_app(data_dir)).get("/api/scan").json()
    assert again["index"]["scanned_at"] == scanned_at
    assert again["index"]["file_count"] == 1


def test_scan_twice_at_once_is_409(client, monkeypatch, tmp_path):
    import threading

    release = threading.Event()
    real_scan = scanner.scan
    monkeypatch.setattr(scanner, "scan", lambda config, progress=None: (release.wait(5), real_scan(config, progress))[1])

    assert client.post("/api/scan").status_code == 202
    assert client.post("/api/scan").status_code == 409
    release.set()
    assert wait_scan(client)["error"] is None
