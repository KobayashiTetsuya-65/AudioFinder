"""FastAPI本体。APIと画面（static/）を配信する。"""

import ntpath
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import storage

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
JST = timezone(timedelta(hours=9))


class RootIn(BaseModel):
    path: str = ""
    label: str = ""


class RootPatch(BaseModel):
    enabled: bool


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


def create_app(data_dir: Path = storage.DEFAULT_DATA_DIR) -> FastAPI:
    storage.load_config(data_dir)  # 初回は config.json を作る
    config_path = data_dir / "config.json"
    lock = threading.Lock()  # config.json の読み→書きが同時に走らないように

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

    # API より後に登録する（"/" 以下をすべて受けるため）
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
