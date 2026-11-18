from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageOps

USER_AGENT = "kpop-concentration-pipeline/0.1 (personal non-commercial use)"


def log(msg: str) -> None:
    print(msg, flush=True)


def warn(msg: str) -> None:
    print(f"[警告] {msg}", file=sys.stderr, flush=True)


class Http:
    """リクエストの間隔を空け、429 / 5xx のときは待ってから再試行する。"""

    def __init__(self, interval: float = 1.0, user_agent: str | None = None):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent or USER_AGENT
        self.interval = interval
        self._last = 0.0
        self._explained_429 = False

    def _wait(self) -> None:
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()

    def get(self, url: str, params: dict | None = None, *, stream: bool = False) -> requests.Response:
        for attempt in range(6):
            self._wait()
            try:
                r = self.session.get(url, params=params, timeout=60, stream=stream)
            except requests.RequestException as e:
                if attempt == 5:
                    raise
                warn(f"通信エラー({e.__class__.__name__})。{5 * (attempt + 1)}秒後に再試行します")
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code == 429 or r.status_code >= 500:
                if attempt == 5:
                    r.raise_for_status()
                wait = max(int(r.headers.get("Retry-After") or 0), 10 * (attempt + 1))
                if r.status_code == 429 and not self._explained_429:
                    self._explained_429 = True
                    warn(f"サーバーの説明: {html_to_text(r.text)[:300]}")
                warn(f"HTTP {r.status_code}({r.url.split('?')[0][:80]})。{wait}秒待って再試行します")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        raise RuntimeError("unreachable")

    def api(self, url: str, params: dict) -> dict:
        data = self.get(url, {**params, "format": "json", "formatversion": "2", "maxlag": "5"}).json()
        if "error" in data:
            code = data["error"].get("code")
            if code == "maxlag":
                time.sleep(5)
                return self.api(url, params)
            raise RuntimeError(f"API error: {data['error']}")
        return data

    def download(self, url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        r = self.get(url, stream=True)
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
        os.replace(tmp, dest)


def read_image(path: Path) -> np.ndarray:
    """EXIF の向きを反映した RGB の配列を返す(日本語のパスでも読める)。"""
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        return np.asarray(im.convert("RGB"))


def save_rgb(path: Path, rgb: np.ndarray, quality: int = 88) -> None:
    Image.fromarray(rgb).save(path, quality=quality)


def save_rgba(path: Path, rgba: np.ndarray) -> None:
    Image.fromarray(rgba, "RGBA").save(path)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_json(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def html_to_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"(?is)<(style|script|head)\b.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def safe_key(s: str) -> str:
    """ファイル名やIDに使える ASCII の文字列にする。"""
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s).strip("._")
    return s[:60] or "x"
