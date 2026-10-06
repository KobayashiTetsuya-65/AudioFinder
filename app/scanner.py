"""登録フォルダを走査して目録（index.json）を作る（SPEC 9.3）。

素材ファイルは読むだけで、書き換え・移動・削除はしない。
"""

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mutagen

from app import storage

JST = timezone(timedelta(hours=9))

# 区切り文字（/ _ - 空白 . 【】 など）で切ったあと、大文字の切れ目・数字の切れ目で分ける。
# "RPGMusic" → rpg music、"CardDraw01" → card draw 01。日本語などはひと続きのまま残す
_CHUNK = re.compile(r"[A-Za-z0-9]+|[^\x00-\x7f]+")
_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


def _to_separators(text: str) -> str:
    """全角の英数字・空白を半角にそろえ、記号（句読点・括弧など）と空白を半角空白にする。"""
    text = unicodedata.normalize("NFKC", text)
    return "".join(" " if unicodedata.category(c)[0] in "PSZC" else c for c in text)


def to_words(*texts: str) -> str:
    words = []
    for text in texts:
        for chunk in _CHUNK.findall(_to_separators(text)):
            if chunk.isascii():
                words += _WORD.findall(chunk)
            else:
                words.append(chunk)
    return " ".join(w.lower() for w in words)


def file_id(root_id: str, rel_path: str) -> str:
    """root_id と rel_path が同じなら、何度スキャンしても同じIDになる。"""
    return hashlib.sha1(f"{root_id}/{rel_path}".encode("utf-8")).hexdigest()[:12]


def likely_bgm(duration_sec, threshold_sec):
    if duration_sec is None:
        return None
    return duration_sec >= threshold_sec


def read_duration(path: Path):
    """長さ（秒、小数1桁）。読めなければ None。"""
    try:
        audio = mutagen.File(path)
        length = audio.info.length if audio is not None else None
    except Exception:  # 壊れたファイルは mutagen がいろいろな例外を出す
        return None
    if not length or length <= 0:
        return None
    return round(length, 1)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, JST).isoformat(timespec="seconds")


def find_files(root_path: Path, extensions) -> list:
    """root_path 以下の対象ファイルの相対パス（区切りは /）を並べて返す。"""
    exts = {e.lower() for e in extensions}
    found = []
    for dirpath, dirnames, filenames in os.walk(root_path):  # 読めないサブフォルダは黙って飛ばす
        dirnames.sort(key=str.casefold)
        for name in sorted(filenames, key=str.casefold):
            if os.path.splitext(name)[1].lower() in exts:
                found.append(Path(dirpath, name).relative_to(root_path).as_posix())
    return found


def make_entry(root: dict, rel_path: str, threshold_sec) -> dict:
    path = Path(root["path"], *rel_path.split("/"))
    st = path.stat()
    duration = read_duration(path)
    filename = rel_path.rsplit("/", 1)[-1]
    folder = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
    return {
        "id": file_id(root["id"], rel_path),
        "root_id": root["id"],
        "rel_path": rel_path,
        "filename": filename,
        "folder": folder,
        "ext": os.path.splitext(filename)[1].lower().lstrip("."),
        "duration_sec": duration,
        "likely_bgm": likely_bgm(duration, threshold_sec),
        "size_bytes": st.st_size,
        "mtime": _iso(st.st_mtime),
        "readable": duration is not None,
        "words": to_words(root["label"], os.path.splitext(rel_path)[0]),
    }


def scan(config: dict, progress=None) -> dict:
    """有効な登録フォルダを走査して目録を返す。見つからないフォルダは missing にして飛ばす。

    progress(done, total) は、ファイルを1件読むたびに呼ばれる。
    """
    extensions = config["scan"]["extensions"]
    threshold = config["scan"]["bgm_threshold_sec"]

    # 先に一覧だけ作って総数を出す（進行バーのため）
    plan = []
    for root in config["roots"]:
        if not root["enabled"]:
            continue
        root_path = Path(root["path"])
        rel_paths = find_files(root_path, extensions) if root_path.is_dir() else None
        plan.append((root, rel_paths))

    total = sum(len(r) for _, r in plan if r is not None)
    done = 0
    if progress:
        progress(done, total)

    roots, files = [], []
    for root, rel_paths in plan:
        if rel_paths is None:
            roots.append({"id": root["id"], "status": "missing", "file_count": 0})
            continue
        count = 0
        for rel_path in rel_paths:
            try:
                files.append(make_entry(root, rel_path, threshold))
                count += 1
            except OSError:
                pass  # 一覧を作ったあとに消えた・読めなくなったファイルは目録に入れない
            done += 1
            if progress:
                progress(done, total)
        roots.append({"id": root["id"], "status": "ok", "file_count": count})

    return {
        "version": 1,
        "scanned_at": datetime.now(JST).isoformat(timespec="seconds"),
        "roots": roots,
        "files": files,
    }


def dumps_index(index: dict) -> str:
    """files だけ1件1行で書く。AIが文字列検索で当たった1行から、そのファイルの情報がすべて読めるように（SPEC 9.3）。"""

    def one(v):
        return json.dumps(v, ensure_ascii=False)

    lines = [
        "{",
        f'  "version": {one(index["version"])},',
        f'  "scanned_at": {one(index["scanned_at"])},',
        f'  "roots": {one(index["roots"])},',
    ]
    if index["files"]:
        lines.append('  "files": [')
        lines.append(",\n".join(json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in index["files"]))
        lines.append("  ]")
    else:
        lines.append('  "files": []')
    lines.append("}")
    return "\n".join(lines) + "\n"


def save_index(data_dir: Path, index: dict) -> None:
    storage.save_text(data_dir / "index.json", dumps_index(index))


def load_index(data_dir: Path):
    """index.json を読む。まだ一度もスキャンしていなければ None。"""
    path = data_dir / "index.json"
    return storage.load_json(path) if path.exists() else None
