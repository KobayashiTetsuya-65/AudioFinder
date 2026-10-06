"""タスク8：履歴（SPEC 8.3・9.5）。AIは偽物に差し替える。"""

import json

import pytest

from app import ai, scanner, storage
from tests.test_search import CONDITIONS, client_with, fake_claude, make_index


def test_successful_search_is_saved_with_copies(data_dir):
    ids = make_index(data_dir, 2)
    runner = fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[1]}]})
    client_with(data_dir, runner).post("/api/search", json={"query": "ボス戦"})

    saved = json.loads((data_dir / "history.json").read_text(encoding="utf-8"))
    assert saved["version"] == 1
    [entry] = saved["entries"]
    assert entry["id"].startswith("h_")
    assert entry["created_at"].endswith("+09:00")
    assert entry["query"] == "ボス戦"
    assert isinstance(entry["elapsed_sec"], float)
    assert entry["conditions"] == CONDITIONS
    # 目録の写し（SPEC 9.5 の項目だけ）
    assert entry["local"] == [{"id": ids[1], "filename": "Boss_1.ogg", "rel_path": "Battle/Boss_1.ogg",
                               "root_label": "Pack", "duration_sec": 95.4}]
    assert entry["sites"] == []


def test_history_is_newest_first(data_dir):
    ids = make_index(data_dir, 1)
    client = client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}]}))
    for q in ("1回目", "2回目", "3回目"):
        client.post("/api/search", json={"query": q})

    entries = client.get("/api/history").json()["entries"]
    assert [e["query"] for e in entries] == ["3回目", "2回目", "1回目"]
    assert len({e["id"] for e in entries}) == 3  # 同じ秒に探してもIDは重ならない


def test_51st_search_drops_the_oldest(data_dir):
    ids = make_index(data_dir, 1)
    client = client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}]}))
    for i in range(51):
        client.post("/api/search", json={"query": f"q{i}"})

    entries = storage.load_history(data_dir)["entries"]
    assert len(entries) == 50
    assert entries[0]["query"] == "q50"
    assert entries[-1]["query"] == "q1"  # 最も古い q0 が消えた


def test_max_entries_follows_config(data_dir):
    ids = make_index(data_dir, 1)
    config = storage.load_config(data_dir)
    config["history"]["max_entries"] = 2
    storage.save_json(data_dir / "config.json", config)
    client = client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}]}))
    for q in ("a", "b", "c"):
        client.post("/api/search", json={"query": q})
    assert [e["query"] for e in storage.load_history(data_dir)["entries"]] == ["c", "b"]


def _timeout_runner(prompt, cwd, timeout_sec):
    raise ai.AIError("時間切れ", "timeout")


@pytest.mark.parametrize("runner, kind", [
    (fake_claude(outer={"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}), "login"),
    (_timeout_runner, "timeout"),
    (fake_claude(outer={"type": "result", "is_error": False, "result": "これはJSONではない"}), "invalid_json"),
])
def test_error_search_is_not_saved(data_dir, runner, kind):
    ids = make_index(data_dir, 1)
    # 先に1件成功させておき、エラーの検索で履歴が増えも変わりもしないことを見る
    client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}]})).post(
        "/api/search", json={"query": "成功"})
    before = (data_dir / "history.json").read_text(encoding="utf-8")

    res = client_with(data_dir, runner).post("/api/search", json={"query": "失敗"})
    assert res.status_code == 502
    assert res.json()["error"]["kind"] == kind
    assert (data_dir / "history.json").read_text(encoding="utf-8") == before


def test_no_history_file_before_first_success(data_dir):
    make_index(data_dir, 1)
    client = client_with(data_dir, _timeout_runner)
    client.post("/api/search", json={"query": "失敗"})
    assert not (data_dir / "history.json").exists()
    assert client.get("/api/history").json() == {"entries": []}


def test_zero_hits_is_still_saved(data_dir):
    make_index(data_dir, 1)
    client = client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": []}))
    client.post("/api/search", json={"query": "なにもない"})
    [entry] = storage.load_history(data_dir)["entries"]
    assert entry["local"] == []


def test_history_marks_files_missing_from_current_index(data_dir):
    ids = make_index(data_dir, 2)
    client = client_with(data_dir, fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}, {"id": ids[1]}]}))
    client.post("/api/search", json={"query": "ボス戦"})

    # 再スキャンで ids[1] が目録から消えた
    index = scanner.load_index(data_dir)
    index["files"] = [f for f in index["files"] if f["id"] != ids[1]]
    scanner.save_index(data_dir, index)

    [entry] = client.get("/api/history").json()["entries"]
    present, gone = entry["local"]
    assert present["missing"] is False and present["readable"] is True and present["likely_bgm"] is True
    assert gone["missing"] is True and gone["readable"] is False and gone["likely_bgm"] is None
    assert gone["filename"] == "Boss_1.ogg"  # 写しは残っている
    # 保存されたファイル自体には、今の目録の状態は書き込まない
    assert "missing" not in storage.load_history(data_dir)["entries"][0]["local"][0]


def test_history_does_not_call_ai(data_dir):
    ids = make_index(data_dir, 1)
    runner = fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[0]}]})
    client = client_with(data_dir, runner)
    client.post("/api/search", json={"query": "ボス戦"})
    client.get("/api/history")
    assert len(runner.calls) == 1
