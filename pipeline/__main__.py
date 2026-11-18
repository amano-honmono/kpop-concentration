"""画像パイプラインのコマンド。

  python -m pipeline fetch   [--members ID,..] [--groups ID,..]   Commons から候補をダウンロード
  python -m pipeline process [--members ..] [--source both|commons|manual] [--force]
                                                                 顔検出・位置合わせ・背景除去
  python -m pipeline build                                       画像を選んで public/cards/ と manifest.json を書き出す
  python -m pipeline review  [--port 8765] [--no-browser]        確認ページを開く(除外・固定を保存できる)
  python -m pipeline all     [--members ..]                      fetch → process → build をまとめて実行

--members はカードID(例: blackpink-jisoo,twice-nayeon)。省略すると groups.yaml で有効な全員。
"""
from __future__ import annotations

import argparse
import sys

from .config import load_groups, load_settings, select_members
from .util import Http, log


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows のコンソールでも日本語を出す
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    p = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "process", "build", "review", "all"):
        sp = sub.add_parser(name)
        if name in ("fetch", "process", "all"):
            sp.add_argument("--members", help="カードIDをカンマ区切りで(例: blackpink-jisoo,twice-nayeon)")
            sp.add_argument("--groups", help="グループIDをカンマ区切りで(例: twice,ive)")
        if name in ("fetch", "all"):
            sp.add_argument("--refresh", action="store_true", help="取得済みのメンバーも取り直す")
        if name in ("process", "all"):
            sp.add_argument("--source", choices=("both", "commons", "manual"), default="both",
                            help="どの画像を処理するか(既定: both)")
            sp.add_argument("--force", action="store_true", help="前回の結果があっても作り直す")
        if name == "review":
            sp.add_argument("--port", type=int, default=8765)
            sp.add_argument("--no-browser", action="store_true")
    args = p.parse_args(argv)

    settings = load_settings()
    groups = load_groups()

    def do_build():
        from .build import build
        from .review import generate
        build(groups, settings)
        path = generate(settings)
        log(f"確認ページ: {path}(python -m pipeline review で開くと除外を保存できます)")

    if args.cmd in ("fetch", "all"):
        from .commons import fetch_member, is_fetched
        c = settings["commons"]
        # API と画像のダウンロードで間隔を共有し、1分あたりの回数を守る
        http = Http(60 / c["requests_per_minute"], c.get("user_agent"))
        targets = select_members(groups, args.members, args.groups)
        if not args.refresh:
            done = [m for m in targets if is_fetched(m, settings)]
            if done:
                log(f"取得済みなので飛ばす: {', '.join(m.key for m in done)}(取り直すには --refresh)")
            targets = [m for m in targets if m not in done]
        log(f"Commons から取得: {len(targets)} 人(1分あたり最大 {c['requests_per_minute']} 回)")
        for i, m in enumerate(targets, 1):
            log(f"[{i}/{len(targets)}]")
            fetch_member(m, settings, http)

    if args.cmd in ("process", "all"):
        from .models import use_project_rembg_cache
        use_project_rembg_cache(settings)
        from .faces import FaceAnalyzer
        from .process import BackgroundRemover, process_member
        analyzer = FaceAnalyzer(settings)
        bg = BackgroundRemover(settings["background"]["model"])
        for m in select_members(groups, args.members, args.groups):
            process_member(m, settings, analyzer, bg, source=args.source, force=args.force)

    if args.cmd in ("build", "process", "all"):
        do_build()

    if args.cmd == "review":
        from .build import build
        from .review import serve
        serve(settings, rebuild=lambda: build(groups, settings), port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
