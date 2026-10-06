"""`python -m app` で起動する。サーバーが応答できるようになったらブラウザを開く。"""

import threading
import time
import urllib.request
import webbrowser

import uvicorn

from app import storage
from app.main import create_app


def _open_browser_when_ready(url: str) -> None:
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "api/health", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(url)


def main() -> None:
    config = storage.load_config()
    host = config["server"]["host"]
    port = config["server"]["port"]
    url = f"http://{host}:{port}/"
    print(f"Audio Finder: {url}  (終了するにはこのウィンドウを閉じてください)")
    threading.Thread(target=_open_browser_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
