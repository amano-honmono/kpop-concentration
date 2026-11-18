"""Wikimedia Commons からライセンスが明記された画像を集める。

- メンバーの Commons カテゴリを max_depth 段下までたどってファイルを集める
- ライセンスが許可リスト(CC BY / CC BY-SA / PD / CC0)のものだけ残す
- 「1人で写っていそうな」順に並べ、上位 max_candidates 枚をダウンロードする
- 作者・ライセンス・元URLを cache/commons/credits.json に保存する
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .config import Member
from .util import Http, html_to_text, log, read_json, warn, write_json

API = "https://commons.wikimedia.org/w/api.php"
IMAGE_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
# Wikimedia の標準サムネイル幅(これ以外の幅は直接リクエストすると拒否される)
# https://www.mediawiki.org/wiki/Common_thumbnail_sizes
STANDARD_WIDTHS = (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)
MIN_THUMB_WIDTH = 500


def _fold(s: str) -> str:
    """大文字小文字・アクセント・記号の違いを無視して比べるための正規化。"""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return "".join(ch for ch in s if ch.isalnum())


def unusable_reason(info: dict, cfg: dict) -> str | None:
    if info.get("mime") not in IMAGE_MIME:
        return "mime"
    if min(info.get("width", 0), info.get("height", 0)) < cfg["min_side"]:
        return "size"
    if (pick_width(info, cfg) or 0) < MIN_THUMB_WIDTH or download_url(info, cfg) is None:
        return "size"
    if not license_ok(info, cfg["licenses"]):
        return "license"
    return None


def walk_category(http: Http, category: str, cfg: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    """カテゴリを浅い順にたどり、ファイルと画像情報を同時に集める(generator で API の回数を減らす)。

    戻り値: (found, infos)。found はファイル名 → {depth, category, pageid}(最初に見つかった浅い方)。
    使える画像が enough_files 枚に達したら、それ以上たどらない。
    """
    found: dict[str, dict] = {}
    infos: dict[str, dict] = {}
    seen = {category}
    frontier = [category]
    for depth in range(cfg["max_depth"] + 1):
        nxt = []
        for cat in frontier:
            cont: dict = {}
            while True:
                d = http.api(API, {
                    "action": "query", "generator": "categorymembers", "gcmtitle": f"Category:{cat}",
                    "gcmtype": "file|subcat", "gcmlimit": "50", "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata", "iiurlwidth": str(cfg["thumb_width"]),  # size はバイト数も含む
                    "iiextmetadatafilter": "License|LicenseShortName|LicenseUrl|Artist|Credit|AttributionRequired",
                    **cont,
                })
                for p in (d.get("query") or {}).get("pages", []):
                    if p["ns"] == 14 and depth < cfg["max_depth"]:
                        sub = p["title"].removeprefix("Category:")
                        if sub not in seen:
                            seen.add(sub)
                            nxt.append(sub)
                    elif p["ns"] == 6 and p["title"].lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        found.setdefault(p["title"], {"depth": depth, "category": cat, "pageid": p["pageid"]})
                        if p.get("imageinfo") and p["title"] not in infos:
                            infos[p["title"]] = {"pageid": p["pageid"], **p["imageinfo"][0]}
                if "continue" not in d:
                    break
                cont = d["continue"]
            if sum(unusable_reason(i, cfg) is None for i in infos.values()) >= cfg["enough_files"]:
                return found, infos
        frontier = nxt
    return found, infos


def fetch_depicts(http: Http, pageids: list[int]) -> dict[int, list[str]]:
    """Structured Data on Commons の「描かれているもの」(P180)。"""
    out: dict[int, list[str]] = {}
    for i in range(0, len(pageids), 50):
        chunk = pageids[i:i + 50]
        d = http.api(API, {"action": "wbgetentities", "ids": "|".join(f"M{p}" for p in chunk), "props": "claims"})
        for mid, ent in (d.get("entities") or {}).items():
            claims = ent.get("statements") or ent.get("claims") or {}
            if not isinstance(claims, dict):
                continue
            qids = []
            for c in claims.get("P180", []):
                v = (c.get("mainsnak") or {}).get("datavalue", {}).get("value")
                if isinstance(v, dict) and "id" in v:
                    qids.append(v["id"])
            out[int(mid[1:])] = qids
    return out


def license_code(info: dict) -> str:
    meta = info.get("extmetadata", {})
    code = (meta.get("License") or {}).get("value", "")
    if not code:
        code = (meta.get("LicenseShortName") or {}).get("value", "").lower().replace(" ", "-")
        if "public-domain" in code:
            code = "pd"
    return code.lower()


def license_ok(info: dict, allowed: list[str]) -> bool:
    code = license_code(info)
    return bool(code) and any(code == a or code.startswith(a + "-") for a in allowed)


def credit_of(title: str, info: dict) -> dict:
    meta = info.get("extmetadata", {})
    return {
        "title": title,
        "author": html_to_text((meta.get("Artist") or {}).get("value")) or "不明",
        "license": (meta.get("LicenseShortName") or {}).get("value") or license_code(info),
        "licenseUrl": (meta.get("LicenseUrl") or {}).get("value", ""),
        "sourceUrl": info.get("descriptionurl", ""),
    }


def rank(member: Member, title: str, found: dict, info: dict, depicts: list[str] | None) -> float:
    """1人で写っている本人の写真ほど高くなる、おおまかな点数。"""
    score = -2.0 * found["depth"]
    folded_title = _fold(title)
    names = {member.name.get("en", ""), member.id, member.real_name or ""}
    names |= {member.real_name.replace("-", "")} if member.real_name else set()
    if any(len(_fold(n)) >= 3 and _fold(n) in folded_title for n in names):
        score += 2
    if "cropped" in title.lower() or "crop" in title.lower():
        score += 1
    if depicts is not None and member.wikidata:
        if member.wikidata in depicts:
            score += 3
            score -= 1.5 * (len(depicts) - 1)  # 他にも何かが写っている(多くは他のメンバー)
        elif depicts:
            score -= 1
    # 解像度が高いほど少しだけ優先
    score += min(info.get("width", 0) * info.get("height", 0), 4_000_000) / 4_000_000
    return score


def pick_width(info: dict, cfg: dict) -> int | None:
    """取得するサムネイルの幅。thumb_width 以下・元画像の幅未満で一番大きい標準サイズ。"""
    w = info.get("width", 0)
    return max((s for s in STANDARD_WIDTHS if s <= cfg["thumb_width"] and s < w), default=None)


def download_url(info: dict, cfg: dict) -> str | None:
    """標準サイズのサムネイルの URL。元画像は取らない(元画像の直接ダウンロードは強く制限されている)。"""
    width = pick_width(info, cfg)
    if width is None:
        return None
    # API の URL には計測用のクエリ(?utm_source=…)が付くことがあるので外す
    thumb = info.get("thumburl", "").split("?", 1)[0]
    if "/thumb/" in thumb:  # iiurlwidth で返ってきたサムネイルの幅を差し替える
        head, _, tail = thumb.rpartition("/")
        return head + "/" + re.sub(r"^\d+px-", f"{width}px-", tail)
    # 元画像が thumb_width より小さいと、API は元画像の URL を返すので、サムネイルの URL を組み立てる
    url = info["url"].split("?", 1)[0]
    m = re.match(r"^(https://upload\.wikimedia\.org/wikipedia/commons)/([0-9a-f]/[0-9a-f]{2})/([^/]+)$", url)
    if not m or info.get("mime") == "image/webp":
        return None
    base, hashpath, name = m.groups()
    return f"{base}/thumb/{hashpath}/{name}/{width}px-{name}"


def fetch_member(member: Member, settings: dict, http: Http) -> list[dict]:
    """メンバー1人分の候補をダウンロードし、files.json を書いて返す。"""
    cfg = settings["commons"]
    root: Path = settings["paths"]["cache"] / "commons"
    member_dir = root / member.key
    if not member.commons_category:
        warn(f"{member.label()}: commons_category がないので Commons からは取得しません")
        return []

    log(f"{member.label()}: カテゴリ「{member.commons_category}」をたどっています")
    found, infos = walk_category(http, member.commons_category, cfg)
    titles = list(found)

    usable = {}
    rejected = {"license": 0, "size": 0, "mime": 0}
    for title, info in infos.items():
        reason = unusable_reason(info, cfg)
        if reason:
            rejected[reason] += 1
        else:
            usable[title] = info

    depicts = fetch_depicts(http, [i["pageid"] for i in usable.values()])
    ranked = sorted(usable, key=lambda t: rank(member, t, found[t], usable[t], depicts.get(usable[t]["pageid"])),
                    reverse=True)
    chosen = ranked[: cfg["max_candidates"]]
    log(f"  画像 {len(titles)} 件 → 使える {len(usable)} 件(ライセンス対象外 {rejected['license']}、"
        f"小さい {rejected['size']}、形式 {rejected['mime']})→ 上位 {len(chosen)} 件をダウンロード")

    credits_path = root / "credits.json"
    credits = read_json(credits_path, {})
    entries = []
    downloaded = 0
    for n, title in enumerate(chosen, 1):
        info = usable[title]
        url = download_url(info, cfg)
        ext = Path(url).suffix.lower()
        local = member_dir / f"{info['pageid']}{ext if ext in ('.jpg', '.jpeg', '.png', '.webp') else IMAGE_MIME[info['mime']]}"
        old = [p for p in member_dir.glob(f"{info['pageid']}.*") if p.suffix != ".part"] if member_dir.exists() else []
        if old:  # 以前のやり方で取得済みのものはそのまま使う
            local = old[0]
        else:
            try:
                http.download(url, local)
                downloaded += 1
            except Exception as e:  # noqa: BLE001 - 1枚の失敗で全体を止めない
                warn(f"  ダウンロード失敗: {title}: {e}")
                continue
        credit = credit_of(title, info)
        credits[local.name] = {"member": member.key, **credit}
        entries.append({
            "key": f"commons-{info['pageid']}", "file": local.name, "source": "commons",
            "depth": found[title]["depth"], "category": found[title]["category"],
            "depicts": depicts.get(info["pageid"]), "credit": credit,
        })
        # 途中で止めても続きから再開できるように毎回保存する
        write_json(member_dir / "files.json", entries)
        write_json(credits_path, credits)
        if n % 10 == 0:
            log(f"  {n}/{len(chosen)}")
    log(f"  完了: {len(entries)} 枚(今回ダウンロード {downloaded} 枚)")
    write_json(member_dir / "done.json", {"files": len(entries), "candidates": len(chosen)})
    return entries


def is_fetched(member: Member, settings: dict) -> bool:
    return (settings["paths"]["cache"] / "commons" / member.key / "done.json").exists()
