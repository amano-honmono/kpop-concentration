"""確認用ページ work/review.html の生成と、除外・固定を保存するローカルサーバー。

`python -m pipeline review` で http://127.0.0.1:8765/ を開く。
ボタンで「除外」「固定」を切り替えると config/exclusions.yaml に保存され、
「選び直す」を押すと build をやり直してページを更新する。
review.html をファイルとして直接開いた場合は、保存の代わりに exclusions.yaml の内容を表示する。
"""
from __future__ import annotations

import json
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_exclusions, save_exclusions
from .util import log, read_json

TEMPLATE = Path(__file__).with_name("review_template.html")


def generate(settings: dict) -> Path:
    work: Path = settings["paths"]["work"]
    data = read_json(work / "review.json", {"members": []})
    payload = json.dumps({"review": data, "exclusions": load_exclusions()}, ensure_ascii=False)
    html = TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload.replace("</", "<\\/"))
    out = work / "review.html"
    out.write_text(html, encoding="utf-8")
    return out


def serve(settings: dict, rebuild, port: int = 8765, open_browser: bool = True) -> None:
    work: Path = settings["paths"]["work"].resolve()
    lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(work), **kwargs)

        def log_message(self, fmt, *args):  # アクセスログは出さない
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self.path = "/review.html"
            super().do_GET()

        def _json(self, code: int, obj) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b"{}"
            try:
                with lock:
                    if self.path == "/api/exclusions":
                        save_exclusions(json.loads(body))
                        return self._json(200, {"ok": True})
                    if self.path == "/api/build":
                        rebuild()
                        generate(settings)
                        return self._json(200, {"ok": True})
                self._json(404, {"ok": False, "error": "not found"})
            except Exception as e:  # noqa: BLE001
                self._json(500, {"ok": False, "error": str(e)})

    generate(settings)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    log(f"確認ページ: {url}(終了するには Ctrl+C)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
