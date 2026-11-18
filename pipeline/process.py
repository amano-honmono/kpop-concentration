"""候補画像を1枚ずつ加工する: 顔検出 → 位置合わせ → 背景除去 → full / face の書き出し。

結果は work/<カードID>/<候補ID>/ に保存する(meta.json, src.jpg, full.png, face.png)。
元画像と加工の設定が前回と同じなら作り直さない。
"""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import yaml

from .config import Member
from .faces import BROW_TOP, CHEEK_L, CHEEK_R, CHIN, FaceAnalyzer, yaw_from_points
from .util import log, read_image, read_json, safe_key, save_rgb, save_rgba, sha1_file, sha1_json, warn, write_json

PROCESS_VERSION = 1
IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp")


# ---------------------------------------------------------------- 候補の一覧

def list_candidates(member: Member, settings: dict, source: str) -> list[dict]:
    out = []
    if source in ("commons", "both"):
        cdir = settings["paths"]["cache"] / "commons" / member.key
        for e in read_json(cdir / "files.json", []):
            path = cdir / e["file"]
            if path.exists():
                out.append({**e, "path": path})
    if source in ("manual", "both"):
        mdir = settings["paths"]["raw"] / member.group_id / member.id
        credits = {}
        if (mdir / "credits.yaml").exists():
            credits = yaml.safe_load((mdir / "credits.yaml").read_text(encoding="utf-8")) or {}
        if mdir.exists():
            for path in sorted(mdir.iterdir()):
                if path.suffix.lower() not in IMAGE_EXT:
                    continue
                c = credits.get(path.name) or {}
                out.append({
                    "key": f"manual-{safe_key(path.stem)}", "file": path.name, "source": "manual", "path": path,
                    "credit": {"title": path.name, "author": c.get("author", "不明(手動で追加)"),
                               "license": c.get("license", "不明"), "licenseUrl": c.get("licenseUrl", ""),
                               "sourceUrl": c.get("sourceUrl", "")},
                })
    return out


# ---------------------------------------------------------------- 幾何

def align_matrix(eye_r: np.ndarray, eye_l: np.ndarray, size: int, eye_distance: float, eye_y: float) -> np.ndarray:
    """両目が水平・間隔が一定・目の中点が (size/2, eye_y*size) に来る相似変換(2x3)。"""
    d = eye_l - eye_r
    angle = math.degrees(math.atan2(d[1], d[0]))
    scale = eye_distance * size / max(float(np.hypot(*d)), 1e-6)
    mid = (eye_r + eye_l) / 2
    m = cv2.getRotationMatrix2D((float(mid[0]), float(mid[1])), angle, scale)
    m[:, 2] += np.array([size / 2, eye_y * size]) - mid
    return m


def transform(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return pts @ m[:, :2].T + m[:, 2]


def ellipse_mask(pts: np.ndarray, size: int, eye_dist_px: float, cfg: dict) -> np.ndarray:
    """位置合わせ後のランドマークから、眉の少し上からあごまでの楕円マスク(0..1)を作る。"""
    cheek_r, cheek_l, chin = pts[CHEEK_R], pts[CHEEK_L], pts[CHIN]
    cx = (cheek_r[0] + cheek_l[0]) / 2
    half_w = cfg["width"] * abs(cheek_l[0] - cheek_r[0]) / 2
    top = pts[list(BROW_TOP)][:, 1].min() - cfg["forehead"] * eye_dist_px
    bottom = chin[1]
    cy, half_h = (top + bottom) / 2, (bottom - top) / 2
    ss = 4  # 縁をなめらかにするため4倍で描いて縮める
    big = np.zeros((size * ss, size * ss), np.uint8)
    cv2.ellipse(big, (round(cx * ss), round(cy * ss)), (round(half_w * ss), round(half_h * ss)),
                0, 0, 360, 255, -1, lineType=cv2.LINE_AA)
    mask = cv2.resize(big, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    if cfg["feather"] > 0:
        k = cfg["feather"] * 2 + 1
        mask = cv2.GaussianBlur(mask, (k, k), 0)
    return mask


def dhash(gray: np.ndarray) -> str:
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (small[:, 1:] > small[:, :-1]).flatten()
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


# ---------------------------------------------------------------- 背景除去

class BackgroundRemover:
    def __init__(self, model: str):
        from rembg import new_session  # 読み込みが重いので必要になってから
        self.session = new_session(model)

    def alpha(self, rgb: np.ndarray) -> np.ndarray:
        from PIL import Image
        from rembg import remove
        mask = remove(Image.fromarray(rgb), session=self.session, only_mask=True, post_process_mask=True)
        return np.asarray(mask, np.float32) / 255


# ---------------------------------------------------------------- 1枚の処理

def settings_hash(settings: dict) -> str:
    keys = ("detect", "align", "face_mask", "background")
    return sha1_json({"v": PROCESS_VERSION, **{k: settings[k] for k in keys}})


def process_one(cand: dict, out_dir: Path, analyzer: FaceAnalyzer, bg: BackgroundRemover, settings: dict) -> dict:
    det, al = settings["detect"], settings["align"]
    size = al["size"]
    meta = {"key": cand["key"], "source": cand["source"], "file": cand["file"], "credit": cand["credit"],
            "commons": {k: cand.get(k) for k in ("depth", "category", "depicts")} if cand["source"] == "commons" else None,
            "status": "ok", "reason": None, "metrics": {}}
    out_dir.mkdir(parents=True, exist_ok=True)

    def reject(reason: str) -> dict:
        meta["status"], meta["reason"] = "rejected", reason
        return meta

    rgb = read_image(cand["path"])
    h, w = rgb.shape[:2]
    thumb_scale = 360 / max(h, w)
    save_rgb(out_dir / "src.jpg", cv2.resize(rgb, (max(1, round(w * thumb_scale)), max(1, round(h * thumb_scale))),
                                             interpolation=cv2.INTER_AREA))
    meta["metrics"]["image_size"] = [w, h]

    faces = analyzer.detect(rgb)
    meta["metrics"]["faces"] = len(faces)
    if len(faces) == 0:
        return reject("顔が見つからない")
    areas = faces[:, 2] * faces[:, 3]
    order = np.argsort(-areas)
    main = faces[order[0]]
    others = int((areas[order[1:]] >= det["other_face_ratio"] * areas[order[0]]).sum())
    meta["metrics"]["other_faces"] = others
    if others > 0:
        return reject(f"複数の顔({others + 1}人)")

    lm = analyzer.landmarks(rgb, main)
    if lm is None:
        return reject("ランドマークを取れない")
    yaw = lm.yaw if not math.isnan(lm.yaw) else yaw_from_points(lm)
    meta["metrics"].update({
        "eye_distance": round(lm.eye_distance, 1), "yaw": round(yaw, 1), "pitch": round(lm.pitch, 1),
        "roll": round(lm.roll, 1), "yaw_points": round(yaw_from_points(lm), 1),
        "upscale": round(al["full"]["eye_distance"] * size / max(lm.eye_distance, 1e-6), 2),
    })
    if lm.eye_distance < det["min_eye_distance"]:
        return reject(f"顔が小さい(目の間隔 {lm.eye_distance:.0f}px)")
    if abs(yaw) > det["max_yaw"]:
        return reject(f"横向き({yaw:+.0f}°)")
    if abs(lm.pitch) > det["max_pitch"]:
        return reject(f"上下を向いている({lm.pitch:+.0f}°)")

    emb = analyzer.embedding(rgb, main)
    ones = np.full((h, w), 255, np.uint8)

    # full: 背景だけ除去
    m_full = align_matrix(lm.eye_right, lm.eye_left, size, **al["full"])
    full_rgb = cv2.warpAffine(rgb, m_full, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
    full_valid = cv2.warpAffine(ones, m_full, (size, size), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
    alpha = bg.alpha(full_rgb) * full_valid
    save_rgba(out_dir / "full.png", np.dstack([full_rgb, (alpha * 255).round().astype(np.uint8)]))

    # face: 楕円で顔だけ残す(拡大して顔をカードいっぱいにする)
    m_face = align_matrix(lm.eye_right, lm.eye_left, size, **al["face"])
    face_rgb = cv2.warpAffine(rgb, m_face, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
    face_valid = cv2.warpAffine(ones, m_face, (size, size), flags=cv2.INTER_LINEAR).astype(np.float32) / 255
    mask = ellipse_mask(transform(m_face, lm.points), size, al["face"]["eye_distance"] * size, settings["face_mask"])
    inside = mask > 0.5
    visible = float(face_valid[inside].mean()) if inside.any() else 0.0
    meta["metrics"]["face_visible"] = round(visible, 3)
    save_rgba(out_dir / "face.png", np.dstack([face_rgb, (mask * face_valid * 255).round().astype(np.uint8)]))

    gray = cv2.cvtColor(face_rgb, cv2.COLOR_RGB2GRAY)
    meta["metrics"]["sharpness"] = round(float(cv2.Laplacian(gray, cv2.CV_64F)[inside].var()), 1)
    meta["dhash"] = dhash(np.where(inside, gray, 0).astype(np.uint8))
    meta["embedding"] = [round(float(v), 5) for v in emb]
    if visible < det["min_face_visible"]:
        return reject(f"顔が画像の端で切れている({visible:.0%})")
    return meta


def process_member(member: Member, settings: dict, analyzer: FaceAnalyzer, bg: BackgroundRemover,
                   source: str = "both", force: bool = False) -> list[dict]:
    cands = list_candidates(member, settings, source)
    if not cands:
        warn(f"{member.label()}: 候補の画像がありません(fetch を実行するか raw/{member.group_id}/{member.id}/ に画像を置く)")
        return []
    work = settings["paths"]["work"] / member.key
    shash = settings_hash(settings)
    metas, done, cached = [], 0, 0
    for cand in cands:
        out_dir = work / cand["key"]
        input_sha1 = sha1_file(cand["path"])
        old = read_json(out_dir / "meta.json")
        if not force and old and old.get("input_sha1") == input_sha1 and old.get("settings_hash") == shash:
            old["credit"] = cand["credit"]
            metas.append(old)
            cached += 1
            continue
        try:
            meta = process_one(cand, out_dir, analyzer, bg, settings)
        except Exception as e:  # noqa: BLE001 - 壊れた画像などで止めない
            warn(f"  {cand['key']}: 処理に失敗しました: {e}")
            meta = {"key": cand["key"], "source": cand["source"], "file": cand["file"], "credit": cand["credit"],
                    "status": "rejected", "reason": f"処理エラー: {e}", "metrics": {}}
        meta["input_sha1"], meta["settings_hash"] = input_sha1, shash
        write_json(out_dir / "meta.json", meta)
        metas.append(meta)
        done += 1
    ok = sum(m["status"] == "ok" for m in metas)
    log(f"{member.label()}: 候補 {len(metas)} 枚(新しく処理 {done}、前回の結果を使用 {cached})→ 条件を満たした {ok} 枚")
    return metas
