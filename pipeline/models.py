"""学習済みモデルのダウンロード(初回だけ)。保存先は cache/models/。"""
from __future__ import annotations

import os
from pathlib import Path

from .util import Http, log

MODELS = {
    # 顔検出(複数の顔を数えるのに使う)
    "yunet": ("face_detection_yunet_2023mar.onnx",
              "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
              100_000),
    # 顔の特徴量(同一人物かどうか・重複の判定)
    "sface": ("face_recognition_sface_2021dec.onnx",
              "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
              10_000_000),
    # MediaPipe Face Landmarker(478点のランドマークと顔の向き)
    "landmarker": ("face_landmarker.task",
                   "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
                   1_000_000),
}


def model_path(settings: dict, name: str) -> Path:
    filename, url, min_size = MODELS[name]
    path = settings["paths"]["cache"] / "models" / filename
    if not path.exists():
        log(f"モデルをダウンロードしています: {filename}")
        Http(interval=0).download(url, path)
        if path.stat().st_size < min_size:  # Git LFS のポインタだけ落ちてきた場合など
            path.unlink()
            raise RuntimeError(f"モデルのダウンロードに失敗しました: {url}")
    return path


def use_project_rembg_cache(settings: dict) -> None:
    """rembg のモデルもプロジェクトの cache/models/u2net に置く。"""
    os.environ.setdefault("U2NET_HOME", str(settings["paths"]["cache"] / "models" / "u2net"))
