import json

import pytest
from fastapi.testclient import TestClient

from app import ai, scanner, storage
from app.main import create_app

CONDITIONS = {"kind": "bgm", "mood": ["緊迫"], "genre": ["オーケストラ"], "tempo": "fast", "loop": True}


def make_index(data_dir, n):
    """f000000000000〜 のIDを持つ n 件の目録を書く。"""
    config = storage.load_config(data_dir)
    config["roots"] = [{"id": "r_1", "label": "Pack", "path": "D:\\Pack", "enabled": True, "added_at": "2026-10-06T21:00:00+09:00"}]
    storage.save_json(data_dir / "config.json", config)
    files = [
        {"id": f"f{i:011d}", "root_id": "r_1", "rel_path": f"Battle/Boss_{i}.ogg", "filename": f"Boss_{i}.ogg",
         "folder": "Battle", "ext": "ogg", "duration_sec": 95.4, "likely_bgm": True, "size_bytes": 1,
         "mtime": "2026-10-06T21:00:00+09:00", "readable": True, "words": f"pack battle boss {i}"}
        for i in range(n)
    ]
    index = {"version": 1, "scanned_at": "2026-10-06T21:30:00+09:00",
             "roots": [{"id": "r_1", "status": "ok", "file_count": n}], "files": files}
    scanner.save_index(data_dir, index)
    return [f["id"] for f in files]


def fake_claude(answer=None, *, outer=None):
    """`claude -p --output-format json` の出力を真似る偽物。呼ばれたときの引数を calls に残す。"""
    calls = []

    def runner(prompt, cwd, timeout_sec):
        calls.append({"prompt": prompt, "cwd": cwd, "timeout_sec": timeout_sec})
        out = outer if outer is not None else {"type": "result", "subtype": "success", "is_error": False,
                                               "result": "", "structured_output": answer}
        return json.dumps(out, ensure_ascii=False)

    runner.calls = calls
    return runner


def client_with(data_dir, runner):
    return TestClient(create_app(data_dir, ai_runner=runner))


# ---------- 正常な応答 ----------

def test_search_returns_conditions_and_local(data_dir):
    ids = make_index(data_dir, 3)
    runner = fake_claude({"conditions": CONDITIONS, "local": [{"id": ids[2]}, {"id": ids[0]}]})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "  ボス戦、緊迫感  "})

    assert res.status_code == 200
    body = res.json()
    assert body["query"] == "ボス戦、緊迫感"
    assert body["conditions"] == CONDITIONS
    assert [t["id"] for t in body["local"]] == [ids[2], ids[0]]  # AIが返した順のまま
    first = body["local"][0]
    assert first == {"id": ids[2], "filename": "Boss_2.ogg", "rel_path": "Battle/Boss_2.ogg", "root_label": "Pack",
                     "duration_sec": 95.4, "likely_bgm": True, "readable": True}
    assert isinstance(body["elapsed_sec"], float)

    # 作業フォルダは data/、待ち時間は config の値、場面説明がAIに渡る
    call = runner.calls[0]
    assert call["cwd"] == data_dir
    assert call["timeout_sec"] == 60
    assert "ボス戦、緊迫感" in call["prompt"]


def test_answer_written_in_result_text_is_also_read(data_dir):
    ids = make_index(data_dir, 1)
    text = "```json\n" + json.dumps({"conditions": CONDITIONS, "local": [{"id": ids[0]}]}) + "\n```"
    runner = fake_claude(outer={"type": "result", "is_error": False, "result": text})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 200
    assert [t["id"] for t in res.json()["local"]] == ids


# ---------- 応答の検証（SPEC 6.4） ----------

def test_ids_not_in_index_are_dropped(data_dir):
    ids = make_index(data_dir, 2)
    local = [{"id": "nothere00000"}, {"id": ids[1]}, {"id": ids[1]}, {"x": 1}, "bad", {"id": ids[0]}]
    runner = fake_claude({"conditions": CONDITIONS, "local": local})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 200
    assert [t["id"] for t in res.json()["local"]] == [ids[1], ids[0]]  # 目録にない・重複・壊れた要素は捨てる


def test_more_than_10_are_truncated(data_dir):
    ids = make_index(data_dir, 12)
    runner = fake_claude({"conditions": CONDITIONS, "local": [{"id": i} for i in ids]})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 200
    assert [t["id"] for t in res.json()["local"]] == ids[:10]


def test_zero_candidates_is_ok(data_dir):
    make_index(data_dir, 1)
    runner = fake_claude({"conditions": {**CONDITIONS, "kind": "se", "tempo": None, "loop": None}, "local": []})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "カードを引く音"})
    assert res.status_code == 200
    assert res.json()["local"] == []
    assert res.json()["conditions"]["kind"] == "se"


def test_odd_condition_values_are_normalized():
    answer = {"conditions": {"kind": "bgm", "mood": ["緊迫", 3, " "], "genre": "x", "tempo": "very fast", "loop": "yes"},
              "local": []}
    assert ai.validate(answer, set())["conditions"] == {"kind": "bgm", "mood": ["緊迫"], "genre": [], "tempo": None, "loop": None}


@pytest.mark.parametrize("answer", [
    {"local": []},                                            # 条件がない
    {"conditions": {**CONDITIONS, "kind": "music"}, "local": []},  # 種類が決められた値でない
    {"conditions": CONDITIONS},                               # 候補の一覧がない
])
def test_malformed_answer_is_error(data_dir, answer):
    make_index(data_dir, 1)
    res = client_with(data_dir, fake_claude(answer)).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 502
    assert "形が正しくありません" in res.json()["detail"]


def test_unreadable_json_is_error(data_dir):
    make_index(data_dir, 1)
    res = client_with(data_dir, lambda *a: "これはJSONではない").post("/api/search", json={"query": "ボス"})
    assert res.status_code == 502
    assert "JSON" in res.json()["detail"]


def test_ai_error_result_is_shown(data_dir):
    make_index(data_dir, 1)
    runner = fake_claude(outer={"type": "result", "is_error": True, "result": "Failed to authenticate"})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 502
    assert "Failed to authenticate" in res.json()["detail"]


# ---------- 入力と目録のチェック ----------

def test_empty_query_is_rejected_without_calling_ai(data_dir):
    make_index(data_dir, 1)
    runner = fake_claude({"conditions": CONDITIONS, "local": []})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "  \n "})
    assert res.status_code == 400
    assert runner.calls == []


def test_no_index_yet(data_dir):
    runner = fake_claude({"conditions": CONDITIONS, "local": []})
    res = client_with(data_dir, runner).post("/api/search", json={"query": "ボス"})
    assert res.status_code == 409
    assert "再スキャン" in res.json()["detail"]
    assert runner.calls == []


# ---------- claude -p の呼び方 ----------

def test_command_allows_only_read_only_tools():
    cmd = ai.build_command("claude")
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert cmd[cmd.index("--tools") + 1] == "Read,Grep,Glob"
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    for flag in ("--dangerously-skip-permissions", "--allowedTools", "--allowed-tools"):
        assert flag not in cmd
    assert ai.PROMPT_PATH.is_file()
    json.loads(cmd[cmd.index("--json-schema") + 1])
