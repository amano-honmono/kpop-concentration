import type { Game } from "../game/engine";
import type { Catalog } from "../manifest";
import { pairKey, submitRecord } from "../storage";
import type { GameSettings } from "../types";
import { asset, formatTime, h } from "./dom";

export interface ResultScreenOptions {
  catalog: Catalog;
  settings: GameSettings;
  game: Game;
  onAgain: () => void;
  onSettings: () => void;
}

export function renderResult(root: HTMLElement, opts: ResultScreenOptions): void {
  const { catalog, game, settings } = opts;
  const timeMs = game.elapsedMs();
  const record = { timeMs, moves: game.moves, misses: game.misses, date: new Date().toISOString() };
  const { fastest, fewestMoves, previous } = submitRecord(settings, record);
  const accuracy = game.moves ? Math.round((game.totalPairs / game.moves) * 100) : 0;

  // メンバーごとの間違い回数と、取り違えた組み合わせ
  const missCount = new Map<string, number>();
  const confused = new Map<string, { a: string; b: string; n: number }>();
  for (const m of game.mistakes) {
    missCount.set(m.a, (missCount.get(m.a) ?? 0) + 1);
    missCount.set(m.b, (missCount.get(m.b) ?? 0) + 1);
    const k = pairKey(m.a, m.b);
    const c = confused.get(k) ?? { a: m.a, b: m.b, n: 0 };
    c.n++;
    confused.set(k, c);
  }

  const score = (label: string, value: string, isNew: boolean) =>
    h("div", { class: "score" }, h("small", {}, label), h("b", {}, value), isNew ? h("span", { class: "badge" }, "ベスト更新") : null);

  const prevBest = previous.fastest
    ? `これまでのベスト: ${formatTime(previous.fastest.timeMs)} / ${previous.fewestMoves?.moves ?? previous.fastest.moves}手`
    : "この設定で初めてのクリアです";

  const members = game.deck.memberIds.map((id) => {
    const m = catalog.member(id);
    const img = game.cards.find((c) => c.memberId === id);
    const n = missCount.get(id) ?? 0;
    return h("li", { class: "member" },
      img ? h("img", { src: asset(img.src), alt: "", loading: "lazy" }) : null,
      h("span", { class: "member-name" }, h("b", {}, m.name.ja), h("small", {}, `${m.name.en} · ${catalog.groupName(m.group)}`)),
      n ? h("span", { class: "miss-badge", title: "このメンバーが絡んだミスの回数" }, `ミス ${n}`) : null);
  });

  const confusedList = [...confused.values()].sort((x, y) => y.n - x.n).map((c) =>
    h("li", {}, h("b", {}, catalog.member(c.a).name.ja), " と ", h("b", {}, catalog.member(c.b).name.ja),
      c.n > 1 ? h("small", {}, ` ×${c.n}`) : null));

  root.replaceChildren(h("div", { class: "screen result" },
    h("section", { class: "panel" },
      h("p", { class: "eyebrow" }, "CLEAR"),
      h("h1", {}, "クリア!"),
      h("div", { class: "scores" },
        score("時間", formatTime(timeMs), fastest),
        score("手数", `${game.moves}手`, fewestMoves),
        score("ミス", `${game.misses}回`, false),
        score("正確さ", `${accuracy}%`, false)),
      h("p", { class: "best" }, prevBest),
      h("div", { class: "actions" },
        h("button", { type: "button", class: "btn primary", onclick: opts.onAgain }, "もう一度"),
        h("button", { type: "button", class: "btn", onclick: opts.onSettings }, "設定に戻る"))),
    h("section", { class: "panel" },
      h("h2", {}, `今回のメンバー(${members.length}人)`),
      h("ul", { class: "members" }, members),
      confusedList.length ? h("h2", {}, "取り違えた組み合わせ") : null,
      confusedList.length ? h("ul", { class: "confused" }, confusedList) : null)));
}
