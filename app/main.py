"""FastAPI本体。APIと画面（static/）を配信する。"""

import ntpath
import re
import secrets
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import ai, scanner, storage

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
JST = timezone(timedelta(hours=9))
FILE_ID = re.compile(r"[0-9a-f]{12}")  # scanner.file_id の形
AUDIO_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg"}


class RootIn(BaseModel):
    path: str = ""
    label: str = ""


class RootPatch(BaseModel):
    enabled: bool


class SearchIn(BaseModel):
    query: str = ""


def _now_jst() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def _clean_path(raw: str) -> str:
    """前後の空白と、エクスプローラーの「パスのコピー」でつく両端の " を外し、区切りや末尾の \\ をそろえる。"""
    p = raw.strip().strip('"').strip()
    return ntpath.normpath(p) if p else ""


def _same_path(a: str, b: str) -> bool:
    """Windowsのパスは大文字小文字を区別しないので、そろえてから比べる。"""
    return ntpath.normcase(ntpath.normpath(a)) == ntpath.normcase(ntpath.normpath(b))


def _new_root_id(roots: list) -> str:
    used = {r["id"] for r in roots}
    while True:
        rid = "r_" + secrets.token_hex(2)
        if rid not in used:
            return rid


def reveal_in_explorer(path: Path) -> None:
    """エクスプローラーで、そのファイルを選択した状態で開く。
    "/select," とパスを別の引数にすると、空白を含むパスでも正しく渡る。explorer は成功しても 1 を返すので終了コードは見ない。
    """
    subprocess.Popen(["explorer", "/select,", str(path)])


def create_app(data_dir: Path = storage.DEFAULT_DATA_DIR, ai_runner=ai.run_claude,
               revealer=reveal_in_explorer) -> FastAPI:
    """ai_runner：`claude -p` を呼ぶ関数。revealer：エクスプローラーを開く関数。テストではどちらも偽物を渡す。"""
    storage.load_config(data_dir)  # 初回は config.json を作る
    config_path = data_dir / "config.json"
    lock = threading.Lock()  # config.json の読み→書きが同時に走らないように
    history_lock = threading.Lock()  # history.json も同じ理由で

    app = FastAPI(title="Audio Finder")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # ---------- 検索対象フォルダ（config.json の roots） ----------

    @app.get("/api/roots")
    def list_roots():
        return {"roots": storage.load_config(data_dir)["roots"]}

    @app.post("/api/roots", status_code=201)
    def add_root(body: RootIn):
        path = _clean_path(body.path)
        if not path:
            raise HTTPException(400, "フォルダのパスを入力してください")
        if not ntpath.isabs(path) or not ntpath.splitdrive(path)[0]:
            raise HTTPException(400, "パスは「D:\\GameAssets\\Audio」のように、ドライブ名から始まる絶対パスで入力してください")

        with lock:
            config = storage.load_config(data_dir)
            dup = next((r for r in config["roots"] if _same_path(r["path"], path)), None)
            if dup:
                raise HTTPException(409, f"このフォルダはすでに「{dup['label']}」として登録されています")

            root = {
                "id": _new_root_id(config["roots"]),
                "label": body.label.strip() or ntpath.basename(path) or path,
                "path": path,
                "enabled": True,
                "added_at": _now_jst(),
            }
            config["roots"].append(root)
            storage.save_json(config_path, config)

        # 外付けドライブを外しているだけのこともあるので、登録はしたうえで警告する
        warning = None
        if not Path(path).is_dir():
            warning = "このフォルダは今は見つかりません（登録はしました）。パスの打ち間違いや、外付けドライブが外れていないか確認してください"
        return {"root": root, "warning": warning}

    @app.patch("/api/roots/{root_id}")
    def update_root(root_id: str, body: RootPatch):
        with lock:
            config = storage.load_config(data_dir)
            root = next((r for r in config["roots"] if r["id"] == root_id), None)
            if root is None:
                raise HTTPException(404, "そのフォルダは登録されていません")
            root["enabled"] = body.enabled
            storage.save_json(config_path, config)
        return {"root": root}

    @app.delete("/api/roots/{root_id}", status_code=204)
    def delete_root(root_id: str):
        with lock:
            config = storage.load_config(data_dir)
            remaining = [r for r in config["roots"] if r["id"] != root_id]
            if len(remaining) == len(config["roots"]):
                raise HTTPException(404, "そのフォルダは登録されていません")
            config["roots"] = remaining
            storage.save_json(config_path, config)

    # ---------- 再スキャン（index.json） ----------

    def _summary(index):
        """画面に出す目録の要約（ファイル一覧は返さない）。"""
        if index is None:
            return None
        return {"scanned_at": index["scanned_at"], "roots": index["roots"], "file_count": len(index["files"])}

    # 要約はメモリに持つ。index.json を毎回開くと、Windowsではスキャン完了時の置き換えとぶつかることがあるため
    scan_state = {"running": False, "done": 0, "total": 0, "error": None, "index": _summary(scanner.load_index(data_dir))}
    scan_lock = threading.Lock()

    def _progress(done, total):
        with scan_lock:
            scan_state.update(done=done, total=total)

    def _run_scan(config):
        error = None
        try:
            index = scanner.scan(config, _progress)
            scanner.save_index(data_dir, index)
        except Exception as e:
            error = f"スキャン中にエラーが起きました：{e}"
        with scan_lock:
            scan_state.update(running=False, error=error)
            if error is None:
                scan_state["index"] = _summary(index)

    @app.post("/api/scan", status_code=202)
    def start_scan():
        with scan_lock:
            if scan_state["running"]:
                raise HTTPException(409, "スキャン中です。終わるまでお待ちください")
            scan_state.update(running=True, done=0, total=0, error=None)
        with lock:
            config = storage.load_config(data_dir)
        threading.Thread(target=_run_scan, args=(config,), daemon=True).start()
        return {"started": True}

    @app.get("/api/scan")
    def scan_status():
        """進行状況と、最後にできた目録の要約。"""
        with scan_lock:
            return dict(scan_state)

    # ---------- 探す（AI） ----------

    @app.post("/api/search")
    def search(body: SearchIn):
        query = body.query.strip()
        if not query:
            raise HTTPException(400, "どんな場面の音を探すか入力してください")
        with lock:
            config = storage.load_config(data_dir)
        index = scanner.load_index(data_dir)
        if index is None:
            raise HTTPException(409, "まだ目録がありません。設定画面でフォルダを登録して「再スキャン」してください")
        files = {f["id"]: f for f in index["files"]}
        labels = {r["id"]: r["label"] for r in config["roots"]}

        # 今は見つからない登録フォルダ（外付けドライブを外しているなど）は飛ばし、画面で注意する（SPEC 10章）
        missing = [r for r in config["roots"] if r["enabled"] and not Path(r["path"]).is_dir()]
        missing_ids = {r["id"] for r in missing}
        known_ids = {fid for fid, f in files.items() if f["root_id"] not in missing_ids}

        searched_at = datetime.now(JST)
        started = time.monotonic()
        try:
            result = ai.search(query, data_dir, known_ids, config["ai"]["timeout_sec"], ai_runner,
                               storage.load_sites(data_dir), config["ai"].get("retry_on_invalid_json", 1))
        except ai.AIError as e:
            # detail は他のAPIと同じく文字列。帯の出し分け用に種類と説明を添える
            return JSONResponse({"detail": str(e), "error": {"kind": e.kind, "hint": e.hint}}, status_code=502)
        elapsed = round(time.monotonic() - started, 1)

        # 画面に出す情報を目録から足す（AIが返すのはIDだけ）
        local = []
        for item in result["local"]:
            f = files[item["id"]]
            local.append({
                "id": f["id"],
                "filename": f["filename"],
                "rel_path": f["rel_path"],
                "root_label": labels.get(f["root_id"], f["root_id"]),
                "duration_sec": f["duration_sec"],
                "likely_bgm": f["likely_bgm"],
                "readable": f["readable"],
            })

        # 成功した検索だけ履歴に残す（SPEC 9.5）。再スキャンや sites.json の編集のあとでも読めるよう、表示に使う値の写しを持つ
        copy_keys = ("id", "filename", "rel_path", "root_label", "duration_sec")
        with history_lock:
            used = {e["id"] for e in storage.load_history(data_dir)["entries"]}
            hid = "h_" + searched_at.strftime("%Y%m%d%H%M%S")
            n = 2
            while hid in used:  # 同じ秒に2回探したとき
                hid = f"h_{searched_at:%Y%m%d%H%M%S}_{n}"
                n += 1
            storage.add_history(data_dir, {
                "id": hid,
                "created_at": searched_at.isoformat(timespec="seconds"),
                "query": query,
                "elapsed_sec": elapsed,
                "conditions": result["conditions"],
                "local": [{k: t[k] for k in copy_keys} for t in local],
                "sites": result["sites"],
            }, config["history"]["max_entries"])

        return {"query": query, "elapsed_sec": elapsed, "conditions": result["conditions"], "local": local,
                "sites": result["sites"],
                "missing_roots": [{"id": r["id"], "label": r["label"], "path": r["path"]} for r in missing]}

    # ---------- 履歴 ----------

    @app.get("/api/history")
    def history():
        """保存された結果を返す（AIは呼ばない）。

        手持ちの素材には今の目録の状態を足す：BGM/SEの印・再生できるか、今の目録にないなら missing。
        """
        with history_lock:
            entries = storage.load_history(data_dir)["entries"]
        index = scanner.load_index(data_dir)
        files = {f["id"]: f for f in index["files"]} if index else {}
        for e in entries:
            for t in e["local"]:
                f = files.get(t["id"])
                t.update(likely_bgm=f["likely_bgm"] if f else None, readable=f["readable"] if f else False,
                         missing=f is None)
        return {"entries": entries}

    # ---------- 試聴・エクスプローラーで開く ----------

    def _file_path(file_id: str):
        """目録のIDから実際のファイルのパスを返す（SPEC 10章 安全面）。

        パスは受け取らない。目録にないID、登録が外れたフォルダ、登録フォルダの外を指すもの、今は無いファイルは404。
        """
        not_found = HTTPException(404, "そのファイルは目録にありません。再スキャンしてください")
        if not FILE_ID.fullmatch(file_id):
            raise not_found
        index = scanner.load_index(data_dir)
        entry = next((f for f in index["files"] if f["id"] == file_id), None) if index else None
        if entry is None:
            raise not_found
        with lock:
            config = storage.load_config(data_dir)
        root = next((r for r in config["roots"] if r["id"] == entry["root_id"]), None)
        if root is None:
            raise not_found
        root_path = Path(root["path"]).resolve()
        path = root_path.joinpath(*entry["rel_path"].split("/")).resolve()
        # 目録が書き換えられていても、登録フォルダの外には触らない
        if not path.is_relative_to(root_path) or not path.is_file():
            raise not_found
        return path, entry

    @app.get("/api/audio/{file_id:path}")  # 「/」を含む不正な要求もここで受けて404にする
    def audio(file_id: str):
        path, entry = _file_path(file_id)
        media_type = AUDIO_TYPES.get(entry["ext"])
        if media_type is None:
            raise HTTPException(404, "このファイルは再生できません")
        # FileResponse は Range 要求に対応しているので、途中への頭出しもできる
        return FileResponse(path, media_type=media_type)

    @app.post("/api/reveal/{file_id:path}", status_code=204)
    def reveal(file_id: str):
        path, _ = _file_path(file_id)
        try:
            revealer(path)
        except OSError as e:
            raise HTTPException(500, f"エクスプローラーを開けませんでした：{e}")

    # API より後に登録する（"/" 以下をすべて受けるため）
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
