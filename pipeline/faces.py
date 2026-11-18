"""顔の検出・ランドマーク・特徴量。

- YuNet(OpenCV): 画像内の顔をすべて見つける。小さい顔にも強いので「顔が1つだけか」の判定に使う
- MediaPipe Face Landmarker: 一番大きい顔の周りを切り出して 478 点のランドマークと顔の向きを取る
- SFace(OpenCV): 顔の特徴量(128次元)。同じメンバーの他の画像と比べて別人や重複を見つける
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from .models import model_path

# MediaPipe のランドマーク番号(画像の左に写る目 = 本人の右目)
RIGHT_EYE = (33, 133)
LEFT_EYE = (362, 263)
CHEEK_R, CHEEK_L = 234, 454
CHIN = 152
NOSE_TIP = 1
BROW_TOP = (105, 334, 66, 296)


@dataclass
class Landmarks:
    points: np.ndarray  # (478, 2) 元画像の座標
    yaw: float
    pitch: float
    roll: float

    @property
    def eye_right(self) -> np.ndarray:
        return self.points[list(RIGHT_EYE)].mean(axis=0)

    @property
    def eye_left(self) -> np.ndarray:
        return self.points[list(LEFT_EYE)].mean(axis=0)

    @property
    def eye_distance(self) -> float:
        return float(np.linalg.norm(self.eye_left - self.eye_right))


def euler_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """MediaPipe の顔の変換行列から (yaw, pitch, roll) を度で返す。"""
    r = np.asarray(m)[:3, :3]
    sy = math.hypot(r[0, 0], r[1, 0])
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.atan2(-r[2, 0], sy))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return yaw, pitch, roll


class FaceAnalyzer:
    def __init__(self, settings: dict):
        self.min_score = settings["detect"]["min_score"]
        self.yunet = cv2.FaceDetectorYN.create(str(model_path(settings, "yunet")), "", (320, 320),
                                               score_threshold=0.5, nms_threshold=0.3, top_k=100)
        self.sface = cv2.FaceRecognizerSF.create(str(model_path(settings, "sface")), "")
        buf = model_path(settings, "landmarker").read_bytes()
        self.landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_buffer=buf),
            num_faces=1, min_face_detection_confidence=0.3, min_face_presence_confidence=0.3,
            output_facial_transformation_matrixes=True))

    def detect(self, rgb: np.ndarray) -> np.ndarray:
        """YuNet の検出結果 (N, 15)。列は x, y, w, h, 5点のランドマーク, score。信頼度で絞り込み済み。"""
        h, w = rgb.shape[:2]
        scale = min(1.0, 1600 / max(h, w))
        img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if scale < 1:
            img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        self.yunet.setInputSize((img.shape[1], img.shape[0]))
        _, faces = self.yunet.detect(img)
        if faces is None:
            return np.zeros((0, 15), np.float32)
        faces = faces.copy()
        faces[:, :14] /= scale
        return faces[faces[:, 14] >= self.min_score]

    def landmarks(self, rgb: np.ndarray, face: np.ndarray) -> Landmarks | None:
        x, y, w, h = face[:4]
        cx, cy = x + w / 2, y + h / 2
        side = 2.2 * max(w, h)
        x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
        s = int(round(side))
        H, W = rgb.shape[:2]
        crop = np.zeros((s, s, 3), np.uint8)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(W, x0 + s), min(H, y0 + s)
        if sx1 <= sx0 or sy1 <= sy0:
            return None
        crop[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
        res = self.landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(crop)))
        if not res.face_landmarks:
            return None
        pts = np.array([[p.x * s + x0, p.y * s + y0] for p in res.face_landmarks[0]], np.float64)
        if res.facial_transformation_matrixes:
            yaw, pitch, roll = euler_from_matrix(res.facial_transformation_matrixes[0])
        else:
            yaw = pitch = roll = float("nan")
        return Landmarks(pts, yaw, pitch, roll)

    def embedding(self, rgb: np.ndarray, face: np.ndarray) -> np.ndarray:
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        aligned = self.sface.alignCrop(bgr, face)
        feat = self.sface.feature(aligned).flatten().astype(np.float64)
        return feat / (np.linalg.norm(feat) + 1e-9)


def yaw_from_points(lm: Landmarks) -> float:
    """変換行列が使えないときの予備: 鼻先が左右の頬のどちらに寄っているかから大まかな角度を出す。"""
    p = lm.points
    left, right, nose = p[CHEEK_R][0], p[CHEEK_L][0], p[NOSE_TIP][0]
    r = (nose - left) / max(right - left, 1e-6)
    return math.degrees(math.asin(float(np.clip((r - 0.5) * 2, -1, 1))))
