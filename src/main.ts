import "./style.css";
import { buildDeck, DeckError } from "./game/deck";
import { Game } from "./game/engine";
import { Catalog, loadManifest, ManifestError } from "./manifest";
import { loadSettings, recordMistakes } from "./storage";
import type { GameSettings } from "./types";
import { renderCredits } from "./ui/credits";
import { h } from "./ui/dom";
import { renderGame } from "./ui/game";
import { renderResult } from "./ui/result";
import { renderSettings } from "./ui/settings";

const root = document.getElementById("app")!;
let cleanup: (() => void) | null = null;
let catalog: Catalog;

function leave(): void {
  cleanup?.();
  cleanup = null;
  window.scrollTo(0, 0);
}

function showSettings(): void {
  leave();
  renderSettings(root, { catalog, onStart: startGame, onCredits: showCredits });
}

function showCredits(): void {
  leave();
  renderCredits(root, catalog, showSettings);
}

async function startGame(settings: GameSettings): Promise<void> {
  leave();
  let game: Game;
  try {
    game = new Game(buildDeck(catalog.manifest, settings));
  } catch (e) {
    if (e instanceof DeckError) {
      alert(e.message);
      return showSettings();
    }
    throw e;
  }
  // 途中でやめても、取り違えた組み合わせは記録しておく(苦手克服モード用)。1ゲームにつき1回だけ
  let saved = false;
  const saveMistakes = () => {
    if (!saved) recordMistakes(game.mistakes);
    saved = true;
  };
  const stop = await renderGame(root, {
    catalog, settings, game,
    onQuit: () => { saveMistakes(); showSettings(); },
    onRetry: () => { saveMistakes(); void startGame(settings); },
    onClear: () => {
      saveMistakes();
      leave();
      renderResult(root, { catalog, settings, game, onAgain: () => void startGame(settings), onSettings: showSettings });
    },
  });
  cleanup = stop;
  if (import.meta.env.DEV) devAutoplay(game);
}

/**
 * 開発用(npm run dev のときだけ): 画面の確認のために自動でめくる
 * - ?demo=clear 最後まで遊んでクリア画面を出す
 * - ?demo=peek  1組そろえ、ミスした2枚を表にしたまま止める
 */
function devAutoplay(game: Game): void {
  const demo = new URLSearchParams(location.search).get("demo");
  const byMember = new Map<string, number[]>();
  for (const c of game.cards) byMember.set(c.memberId, [...(byMember.get(c.memberId) ?? []), c.uid]);
  const groups = [...byMember.values()];
  if (demo === "peek" && groups.length >= 3) {
    game.hideMiss = () => {}; // ミスの2枚を表にしたままにする
    const [a, b, c] = groups;
    const steps = [a[0], a[1], b[0], c[0]];
    steps.forEach((uid, i) => window.setTimeout(() => game.flip(uid), 300 + i * 150));
    return;
  }
  if (demo !== "clear") return;
  const queue: number[] = [];
  // 最初に1回わざと間違えてから、順にそろえる
  if (groups.length >= 2) queue.push(groups[0][0], groups[1][0]);
  for (const uids of groups) queue.push(...uids);
  const step = () => {
    const uid = queue.shift();
    if (uid === undefined || game.finished) return;
    game.flip(uid);
    window.setTimeout(step, 120);
  };
  window.setTimeout(step, 300);
}

async function boot(): Promise<void> {
  try {
    catalog = new Catalog(await loadManifest());
  } catch (e) {
    const msg = e instanceof ManifestError ? e.message : String(e);
    root.replaceChildren(h("div", { class: "screen center" }, h("section", { class: "panel" },
      h("h1", {}, "カード画像がありません"),
      h("p", {}, msg),
      h("p", {}, "先に画像パイプラインを実行してください:"),
      h("pre", {}, ".\\.venv\\Scripts\\python.exe -m pipeline all"))));
    return;
  }
  const demo = import.meta.env.DEV ? new URLSearchParams(location.search).get("demo") : null;
  if (demo === "credits") return showCredits();
  if (demo === "game" || demo === "clear" || demo === "peek") {
    const saved = loadSettings();
    const groupIds = catalog.manifest.groups.map((g) => g.id);
    return void startGame({
      groupIds, pairs: saved.pairs ?? 6, mode: saved.mode ?? "full", samePhoto: false,
      ...(new URLSearchParams(location.search).get("mode") === "face" ? { mode: "face" as const } : {}),
    });
  }
  showSettings();
}

void boot();
