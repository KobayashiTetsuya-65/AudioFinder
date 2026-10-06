"""data/ 内のJSONファイルの読み書き（SPEC 9章）。

書き込みは一時ファイルに書いてから置き換える。途中で落ちても元のファイルが壊れないようにするため。
"""

import copy
import json
import os
import tempfile
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# SPEC 9.2 の初期値
DEFAULT_CONFIG = {
    "version": 1,
    "server": {"host": "127.0.0.1", "port": 8765},
    "ai": {"timeout_sec": 60, "retry_on_invalid_json": 1},
    "scan": {"extensions": [".wav", ".mp3", ".ogg"], "bgm_threshold_sec": 30},
    "history": {"max_entries": 50},
    "roots": [],
}


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def save_json(path: Path, data) -> None:
    save_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_sites(data_dir: Path = DEFAULT_DATA_DIR) -> list:
    """sites.json（手で編集する誘導先サイトの一覧、SPEC 9.6）の sites を返す。ファイルがなければ空。"""
    path = data_dir / "sites.json"
    if not path.exists():
        return []
    return load_json(path)["sites"]


def load_history(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    """history.json（検索履歴、SPEC 9.5）を読む。なければ空の履歴を返す（ファイルを作るのは最初に保存するとき）。"""
    path = data_dir / "history.json"
    if not path.exists():
        return {"version": 1, "entries": []}
    return load_json(path)


def add_history(data_dir: Path, entry: dict, max_entries: int) -> None:
    """履歴の先頭（新しい順）に1件足し、max_entries を超えた分は最も古いものから消す。"""
    history = load_history(data_dir)
    history["entries"] = [entry, *history["entries"]][:max_entries]
    save_json(data_dir / "history.json", history)


def load_config(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    """config.json を読む。なければ初期値で作ってから返す。"""
    path = data_dir / "config.json"
    if not path.exists():
        save_json(path, DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    return load_json(path)
