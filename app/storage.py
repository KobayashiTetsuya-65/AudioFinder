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


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_config(data_dir: Path = DEFAULT_DATA_DIR) -> dict:
    """config.json を読む。なければ初期値で作ってから返す。"""
    path = data_dir / "config.json"
    if not path.exists():
        save_json(path, DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    return load_json(path)
