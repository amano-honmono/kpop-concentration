import type { Card } from "../game/deck";
import { Game } from "../game/engine";
import type { Catalog } from "../manifest";
import type { GameSettings } from "../types";
import { asset, formatTime, h, preload } from "./dom";

/** ミスした2枚を表にしておく時間 */
const MISS_SHOW_MS = 1400;
/** ペアが成立してから、クリア画面を出すまでの間 */
const CLEAR_DELAY_MS = 900;
/** 大きい画面でカードが大きくなりすぎないように */
const MAX_CARD_PX = 220;

export interface GameScreenOptions {
  catalog: Catalog;
  settings: GameSettings;
  game: Game;
  onQuit: () => void;
  onRetry: () => void;
  onClear: (game: Game) => void;
}

/** カードの枚数と盤面の大きさから、カードが一番大きくなる列数を選ぶ */
export function bestColumns(count: number, width: number, height: number, gap: number): { cols: number; size: number } {
  let best = { cols: 1, size: 0 };
  for (let cols = 1; cols <= count; cols++) {
    const rows = Math.ceil(count / cols);
    const size = Math.min((width - gap * (cols - 1)) / cols, (height - gap * (rows - 1)) / rows);
    if (size > best.size) best = { cols, size };
  }
  return best;
}

export async function renderGame(root: HTMLElement, opts: GameScreenOptions): Promise<() => void> {
  const { catalog, game, settings } = opts;
  const cleanups: (() => void)[] = [];

  // 画像を先に読み込む
  const loading = h("p", { class: "loading" }, "カードを準備しています…");
  root.replaceChildren(h("div", { class: "screen center" }, loading));
  await preload(game.cards.map((c) => asset(c.src)), (done, total) => {
    loading.textContent = `カードを準備しています… ${done}/${total}`;
  });

  const stat = (label: string) => {
    const value = h("b", {}, "0");
    return { el: h("span", { class: "stat" }, h("small", {}, label), value), value };
  };
  const moves = stat("手数");
  const misses = stat("ミス");
  const time = stat("時間");
  const pairs = stat("ペア");
  const toast = h("div", { class: "toast", role: "status", "aria-live": "polite" });
  const board = h("div", { class: `board mode-${settings.mode}` });
  const cardEls = new Map<number, HTMLButtonElement>();

  const label = (card: Card) => {
    const m = catalog.member(card.memberId);
    return h("span", { class: "label" }, h("b", {}, m.name.ja), h("small", {}, catalog.groupName(m.group)));
  };

  for (const [i, card] of game.cards.entries()) {
    const btn = h("button", {
      type: "button", class: "card", "aria-label": `カード ${i + 1}`,
      onclick: () => game.flip(card.uid),
    },
    h("span", { class: "card-inner" },
      h("span", { class: "card-face card-back" }, h("span", { class: "back-mark" }, "?")),
      h("span", { class: "card-face card-front" },
        h("img", { src: asset(card.src), alt: "", draggable: "false" }),
        label(card))));
    cardEls.set(card.uid, btn);
    board.append(btn);
  }

  function refreshStats(): void {
    moves.value.textContent = String(game.moves);
    misses.value.textContent = String(game.misses);
    pairs.value.textContent = `${game.matchedPairs}/${game.totalPairs}`;
    time.value.textContent = formatTime(game.elapsedMs());
  }

  let toastTimer = 0;
  function say(content: (Node | string)[], kind: "match" | "miss"): void {
    toast.replaceChildren(...content);
    toast.className = `toast show ${kind}`;
    clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.className = "toast"; }, kind === "miss" ? MISS_SHOW_MS : 1800);
  }

  const name = (id: string) => catalog.member(id).name.ja;
  let missTimer = 0;
  cleanups.push(game.on((e) => {
    switch (e.type) {
      case "flip": {
        const el = cardEls.get(e.card.uid)!;
        el.classList.add("is-up");
        el.setAttribute("aria-label", "表のカード");
        break;
      }
      case "match": {
        for (const c of e.cards) {
          const el = cardEls.get(c.uid)!;
          el.classList.add("is-matched");
          el.setAttribute("aria-label", `${name(c.memberId)}(ペア成立)`);
        }
        const m = catalog.member(e.cards[0].memberId);
        say([h("b", {}, m.name.ja), ` ${m.name.en} · ${catalog.groupName(m.group)}`], "match");
        break;
      }
      case "miss": {
        for (const c of e.cards) cardEls.get(c.uid)!.classList.add("is-miss");
        const [a, b] = e.cards;
        say([h("b", {}, name(a.memberId)), " と ", h("b", {}, name(b.memberId)), " でした"], "miss");
        missTimer = window.setTimeout(() => game.hideMiss(), MISS_SHOW_MS);
        break;
      }
      case "hide": {
        clearTimeout(missTimer);
        for (const c of e.cards) {
          const el = cardEls.get(c.uid)!;
          el.classList.remove("is-up", "is-miss");
          el.setAttribute("aria-label", "カード");
        }
        break;
      }
      case "clear":
        refreshStats();
        window.setTimeout(() => opts.onClear(game), CLEAR_DELAY_MS);
        break;
    }
    refreshStats();
  }));

  const ticker = window.setInterval(() => {
    if (!game.finished) time.value.textContent = formatTime(game.elapsedMs());
  }, 250);
  cleanups.push(() => { clearInterval(ticker); clearTimeout(missTimer); clearTimeout(toastTimer); });

  const groupNote = game.deck.groupId ? h("span", { class: "group-note" }, catalog.groupName(game.deck.groupId)) : null;
  root.replaceChildren(h("div", { class: "screen game" },
    h("header", { class: "hud" },
      h("button", { type: "button", class: "btn ghost small", onclick: opts.onQuit }, "やめる"),
      h("div", { class: "stats" }, moves.el, misses.el, time.el, pairs.el),
      h("button", { type: "button", class: "btn ghost small", onclick: opts.onRetry }, "やり直す")),
    groupNote,
    h("div", { class: "board-wrap" }, board),
    toast));
  refreshStats();

  // 盤面の大きさに合わせて列数とカードの大きさを決める
  const wrap = board.parentElement!;
  const layout = () => {
    const gap = wrap.clientWidth < 480 ? 6 : 10;
    const { cols, size } = bestColumns(game.cards.length, wrap.clientWidth, wrap.clientHeight, gap);
    board.style.setProperty("--cols", String(cols));
    board.style.setProperty("--card", `${Math.floor(Math.min(size, MAX_CARD_PX))}px`);
    board.style.setProperty("--gap", `${gap}px`);
  };
  const ro = new ResizeObserver(layout);
  ro.observe(wrap);
  layout();
  cleanups.push(() => ro.disconnect());

  return () => cleanups.forEach((f) => f());
}
