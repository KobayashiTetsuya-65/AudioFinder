"""FastAPI本体。APIと画面（static/）を配信する。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import storage

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def create_app(data_dir: Path = storage.DEFAULT_DATA_DIR) -> FastAPI:
    storage.load_config(data_dir)  # 初回は config.json を作る

    app = FastAPI(title="Audio Finder")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # API より後に登録する（"/" 以下をすべて受けるため）
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
