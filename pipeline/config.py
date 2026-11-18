from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"


@dataclass
class Member:
    group_id: str
    id: str
    name: dict
    real_name: str | None = None
    wikidata: str | None = None
    commons_category: str | None = None
    status: str = "active"
    enabled: bool = True

    @property
    def key(self) -> str:
        return f"{self.group_id}-{self.id}"

    def label(self) -> str:
        return f"{self.key}({self.name.get('ja', '')})"


@dataclass
class Group:
    id: str
    name: dict
    aliases: list = field(default_factory=list)
    wikidata: str | None = None
    enabled: bool = True
    members: list[Member] = field(default_factory=list)


def load_groups(path: Path = CONFIG_DIR / "groups.yaml") -> list[Group]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    groups = []
    seen = set()
    for g in data["groups"]:
        group = Group(id=g["id"], name=g["name"], aliases=g.get("aliases", []),
                      wikidata=g.get("wikidata"), enabled=g.get("enabled", True))
        for m in g["members"]:
            member = Member(group_id=group.id, id=m["id"], name=m["name"], real_name=m.get("real_name"),
                            wikidata=m.get("wikidata"), commons_category=m.get("commons_category"),
                            status=m.get("status", "active"), enabled=m.get("enabled", True))
            if member.key in seen:
                raise ValueError(f"groups.yaml: ID が重複しています: {member.key}")
            seen.add(member.key)
            group.members.append(member)
        groups.append(group)
    return groups


def load_settings(path: Path = CONFIG_DIR / "pipeline.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        s = yaml.safe_load(f)
    s["paths"] = {k: (ROOT / v).resolve() for k, v in s["paths"].items()}
    return s


def enabled_members(groups: list[Group]) -> list[Member]:
    return [m for g in groups if g.enabled for m in g.members if m.enabled]


def select_members(groups: list[Group], members: str | None = None, group_ids: str | None = None) -> list[Member]:
    """--members(カンマ区切りのカードID)と --groups から対象を決める。どちらもなければ有効な全員。"""
    every = {m.key: m for g in groups for m in g.members}
    if members:
        out = []
        for key in [k.strip() for k in members.split(",") if k.strip()]:
            if key not in every:
                raise SystemExit(f"不明なメンバー: {key}(例: blackpink-jisoo)")
            out.append(every[key])
        return out
    pool = enabled_members(groups)
    if group_ids:
        wanted = {g.strip() for g in group_ids.split(",")}
        unknown = wanted - {g.id for g in groups}
        if unknown:
            raise SystemExit(f"不明なグループ: {', '.join(sorted(unknown))}")
        pool = [m for m in pool if m.group_id in wanted]
    return pool


def load_exclusions(path: Path = CONFIG_DIR / "exclusions.yaml") -> dict[str, dict[str, list[str]]]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {k: {"exclude": list(v.get("exclude") or []), "include": list(v.get("include") or [])}
            for k, v in data.items()}


def save_exclusions(data: dict, path: Path = CONFIG_DIR / "exclusions.yaml") -> None:
    clean = {k: {kk: sorted(set(vv)) for kk, vv in v.items() if vv} for k, v in sorted(data.items())}
    clean = {k: v for k, v in clean.items() if v}
    header = ("# review.html で選んだ除外(exclude)と固定(include)。手で編集してもよい\n"
              "# キーはカードID、値は候補のID(review.html の各画像の下に表示)\n")
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        if clean:
            yaml.safe_dump(clean, f, allow_unicode=True, sort_keys=True)
