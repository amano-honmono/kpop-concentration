"""加工済みの候補からカードに使う画像を選び、public/cards/ と manifest.json を書き出す。

選び方
1. 加工の条件(顔が1つ、正面、十分な大きさ…)を満たした候補だけを使う
2. review.html で「除外」した候補を外す
3. 同じメンバーの他の候補との類似度(中央値)が低いものは「別人の疑い」として外す
4. 品質の点数が高い順に、すでに選んだ画像と重複しないものを選ぶ(「固定」した候補は最優先)
"""
from __future__ import annotations

import datetime as dt
import re
import shutil

import numpy as np
from PIL import Image

from .config import Group, enabled_members, load_exclusions
from .process import list_candidates
from .util import log, read_json, warn, write_json


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def event_key(title: str) -> str:
    """ファイル名から連番・括弧・拡張子を取り除いて、同じ撮影(イベント)の写真をまとめるキーにする。

    "File:Kim Ji-soo at Incheon Airport to Japan on October 05, 2018 (16).png"
    → "kim ji-soo at incheon airport to japan on october 05, 2018"
    """
    s = re.sub(r"^file:", "", title.strip(), flags=re.I)
    s = re.sub(r"\.(jpe?g|png|webp)$", "", s, flags=re.I).lower().replace("_", " ")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\bcropped\b", " ", s)
    s = re.sub(r"[\s\-,.]+\d{1,3}$", "", s.strip())  # 区切りの後の1〜3桁の連番だけ(年や日付は残す)
    return re.sub(r"\s+", " ", s).strip() or title


def quality(meta: dict, settings: dict) -> float:
    m = meta["metrics"]
    res = min(m["eye_distance"] / 100, 1.0)                    # 解像度(元画像の目の間隔)
    sharp = min(np.log1p(m["sharpness"]) / np.log1p(400), 1.0)  # くっきりしているか
    frontal = 1 - min(abs(m["yaw"]) / settings["detect"]["max_yaw"], 1.0)
    ident = meta.get("identity")
    ident = 0.5 if ident is None else max(min(ident, 1.0), 0.0)
    return round(0.35 * res + 0.25 * sharp + 0.2 * frontal + 0.2 * ident, 4)


def select(metas: list[dict], excl: dict, settings: dict) -> list[dict]:
    """各 meta に decision(selected / excluded / suspect / duplicate / unused / rejected)を付け、選んだものを返す。"""
    cfg = settings["select"]
    exclude, include = set(excl.get("exclude", [])), set(excl.get("include", []))
    for m in metas:
        m["decision"], m["note"], m["identity"], m["quality"], m["rank"] = None, None, None, None, None
        if m["status"] != "ok":
            m["decision"] = "rejected"
        elif m["key"] in exclude:
            m["decision"] = "excluded"

    pool = [m for m in metas if m["decision"] is None]
    if len(pool) >= 2:
        emb = np.array([m["embedding"] for m in pool])
        sims = emb @ emb.T
        np.fill_diagonal(sims, np.nan)
        for m, row in zip(pool, sims):
            m["identity"] = round(float(np.nanmedian(row)), 3)
        if len(pool) >= 3:
            for m in pool:
                if m["identity"] < cfg["identity_threshold"] and m["key"] not in include:
                    m["decision"] = "suspect"
                    m["note"] = f"他の候補との類似度 {m['identity']:.2f}"
        elif pool[0]["identity"] < cfg["identity_threshold"]:
            for m in pool:
                m["note"] = "候補が2枚だけで、互いに似ていない(要確認)"

    pool = [m for m in pool if m["decision"] is None]
    for m in pool:
        m["quality"] = quality(m, settings)
    pool.sort(key=lambda m: (m["key"] not in include, -m["quality"]))

    def duplicate_of(m: dict, chosen: list[dict]) -> tuple[dict, float] | None:
        if m["key"] in include:
            return None
        for c in chosen:
            sim = float(np.dot(m["embedding"], c["embedding"]))
            if sim >= cfg["duplicate_similarity"] or hamming(m["dhash"], c["dhash"]) <= cfg["duplicate_hash_distance"]:
                return c, sim
        return None

    def source_group(m: dict) -> str:
        return event_key((m.get("credit") or {}).get("title") or m["file"])

    chosen: list[dict] = []
    # 1周目は同じイベント(撮影)から1枚まで、2周目で残りを埋める。
    # 同じイベントの写真どうしは服や髪型が同じで、ペアが簡単に見つかってしまうため
    passes = (True, False) if cfg.get("one_per_event", True) else (False,)
    for diverse in passes:
        used_groups = {source_group(c) for c in chosen}
        for m in pool:
            if m["decision"] is not None or len(chosen) >= cfg["max_per_member"]:
                continue
            if diverse and source_group(m) in used_groups and m["key"] not in include:
                continue
            dup = duplicate_of(m, chosen)
            if dup:
                m["decision"] = "duplicate"
                m["note"] = f"{dup[0]['key']} と重複(類似度 {dup[1]:.2f})"
                continue
            m["decision"] = "selected"
            chosen.append(m)
            m["rank"] = len(chosen)
            used_groups.add(source_group(m))
    for m in pool:
        if m["decision"] is None:
            m["decision"] = "unused"
    return chosen


def export_member(member_key: str, chosen: list[dict], settings: dict) -> list[dict]:
    out_dir = settings["paths"]["output"] / member_key
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    work = settings["paths"]["work"] / member_key
    q = settings["export"]["webp_quality"]
    images = []
    for n, m in enumerate(chosen, 1):
        entry = {"key": m["key"]}
        for mode in ("full", "face"):
            with Image.open(work / m["key"] / f"{mode}.png") as im:
                im.save(out_dir / f"{n}_{mode}.webp", "WEBP", quality=q, method=6)
            entry[mode] = f"cards/{member_key}/{n}_{mode}.webp"
        entry["credit"] = f"{member_key}/{m['key']}"
        images.append(entry)
    return images


def build(groups: list[Group], settings: dict) -> dict:
    exclusions = load_exclusions()
    cfg = settings["select"]
    out_root = settings["paths"]["output"]
    out_root.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "generatedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                "groups": [], "members": [], "credits": {}}
    review = {"generatedAt": manifest["generatedAt"], "members": []}
    active = {m.key for m in enabled_members(groups)}

    for g in groups:
        group_members = []
        for member in g.members:
            if member.key not in active:
                continue
            keys = [c["key"] for c in list_candidates(member, settings, "both")]
            metas = [m for k in keys if (m := read_json(settings["paths"]["work"] / member.key / k / "meta.json"))]
            if not metas:
                continue
            chosen = select(metas, exclusions.get(member.key, {}), settings)
            status = "ok"
            if len(chosen) < cfg["min_per_member"]:
                warn(f"{member.label()}: 使える画像が {len(chosen)} 枚しかないのでスキップします"
                     f"(最低 {cfg['min_per_member']} 枚)")
                status = "skipped"
                stale = out_root / member.key
                if stale.exists():
                    shutil.rmtree(stale)
            else:
                images = export_member(member.key, chosen, settings)
                for m in chosen:
                    manifest["credits"][f"{member.key}/{m['key']}"] = {**m["credit"], "source": m["source"],
                                                     "modified": "トリミング・回転・拡大縮小・背景除去"}
                manifest["members"].append({"id": member.key, "group": g.id, "name": member.name, "images": images})
                group_members.append(member.key)
            review["members"].append({
                "id": member.key, "group": g.id, "name": member.name, "status": status,
                "selected": len(chosen),
                "candidates": [{k: v for k, v in m.items() if k not in ("embedding",)} for m in metas],
            })
        if group_members:
            manifest["groups"].append({"id": g.id, "name": g.name, "aliases": g.aliases, "members": group_members})

    write_json(out_root / "manifest.json", manifest)
    write_json(settings["paths"]["work"] / "review.json", review)
    n_img = sum(len(m["images"]) for m in manifest["members"])
    log(f"manifest.json: {len(manifest['members'])} 人・{n_img} 枚 → {out_root / 'manifest.json'}")
    return review
