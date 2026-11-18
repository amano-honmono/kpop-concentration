import { checkSettings, maxPairs, membersOf } from "../game/deck";
import type { Catalog } from "../manifest";
import { loadBest, loadSettings, saveSettings } from "../storage";
import { type GameSettings, type ImageMode, PAIR_OPTIONS } from "../types";
import { asset, formatTime, h } from "./dom";

export interface SettingsScreenOptions {
  catalog: Catalog;
  onStart: (s: GameSettings) => void;
  onCredits: () => void;
}

function initialSettings(catalog: Catalog): GameSettings {
  const saved = loadSettings();
  const known = new Set(catalog.manifest.groups.map((g) => g.id));
  const groupIds = (saved.groupIds ?? []).filter((g) => known.has(g));
  return {
    groupIds: groupIds.length ? groupIds : [...known],
    pairs: saved.pairs && (PAIR_OPTIONS as readonly number[]).includes(saved.pairs) ? saved.pairs : 8,
    mode: saved.mode === "face" ? "face" : "full",
    samePhoto: saved.samePhoto ?? false,
  };
}

export function renderSettings(root: HTMLElement, opts: SettingsScreenOptions): void {
  const { catalog } = opts;
  const manifest = catalog.manifest;
  const s = initialSettings(catalog);
  const totalImages = manifest.members.reduce((n, m) => n + m.images.length, 0);

  const groupList = h("div", { class: "chips" });
  const pairList = h("div", { class: "segmented", role: "radiogroup", "aria-label": "ペアの数" });
  const modeList = h("div", { class: "modes", role: "radiogroup", "aria-label": "画像" });
  const sameToggle = h("input", { type: "checkbox", id: "same" });
  const best = h("p", { class: "best" });
  const problem = h("p", { class: "problem", role: "alert" });
  const start = h("button", { class: "btn primary big", type: "button" }, "スタート");

  // 画像モードの見本(最初のメンバーの1枚目)
  const sample = manifest.members[0]?.images[0];

  function update(): void {
    sameToggle.checked = s.samePhoto;

    groupList.replaceChildren(...manifest.groups.map((g) => {
      const on = s.groupIds.includes(g.id);
      const count = membersOf(manifest, [g.id]).length;
      return h("button", {
        type: "button", class: `chip${on ? " on" : ""}`, "aria-pressed": on ? "true" : "false",
        onclick: () => {
          s.groupIds = on ? s.groupIds.filter((x) => x !== g.id) : [...s.groupIds, g.id];
          update();
        },
      }, h("span", { class: "chip-name" }, g.name.en), h("span", { class: "chip-count" }, `${count}人`));
    }));

    const limit = maxPairs(membersOf(manifest, s.groupIds), s.samePhoto);
    // 選んでいる組数が作れないときは、作れる中で一番多い組数にする
    if (s.pairs > limit) {
      const fit = PAIR_OPTIONS.filter((n) => n <= limit);
      if (fit.length) s.pairs = fit[fit.length - 1];
    }
    pairList.replaceChildren(...PAIR_OPTIONS.map((n) => {
      const disabled = n > limit;
      return h("button", {
        type: "button", role: "radio", class: `seg${s.pairs === n ? " on" : ""}`,
        "aria-checked": s.pairs === n ? "true" : "false", disabled,
        title: disabled ? `この選び方では最大 ${limit} 組です` : null,
        onclick: () => { s.pairs = n; update(); },
      }, h("b", {}, n), h("small", {}, `${n * 2}枚`));
    }));

    const modes: [ImageMode, string, string][] = [
      ["full", "髪型も見える", "背景だけ消した写真"],
      ["face", "顔だけ", "上級者向け"],
    ];
    modeList.replaceChildren(...modes.map(([mode, title, note]) => h("button", {
      type: "button", role: "radio", class: `mode${s.mode === mode ? " on" : ""}`,
      "aria-checked": s.mode === mode ? "true" : "false",
      onclick: () => { s.mode = mode; update(); },
    },
    sample ? h("img", { src: asset(sample[mode]), alt: "", loading: "lazy" }) : null,
    h("span", { class: "mode-text" }, h("b", {}, title), h("small", {}, note)))));

    const err = checkSettings(manifest, s);
    problem.textContent = err ?? "";
    start.disabled = !!err;
    const b = err ? {} : loadBest(s);
    best.replaceChildren(...(b.fastest
      ? ["この設定のベスト: ", h("b", {}, formatTime(b.fastest.timeMs)), " / ",
        h("b", {}, `${b.fewestMoves?.moves ?? b.fastest.moves}手`)]
      : [err ? "" : "この設定ではまだ記録がありません"]));
  }

  sameToggle.addEventListener("change", () => { s.samePhoto = sameToggle.checked; update(); });
  start.addEventListener("click", () => {
    if (checkSettings(manifest, s)) return;
    saveSettings(s);
    opts.onStart({ ...s, groupIds: [...s.groupIds] });
  });

  root.replaceChildren(h("div", { class: "screen settings" },
    h("header", { class: "hero" },
      h("p", { class: "eyebrow" }, "K-POP"),
      h("h1", {}, "顔当て神経衰弱"),
      h("p", { class: "lead" }, "同じ人の、ちがう写真をそろえよう")),
    h("section", { class: "panel" },
      h("div", { class: "field" },
        h("div", { class: "field-head" },
          h("h2", {}, "グループ"),
          h("span", { class: "links" },
            h("button", { type: "button", class: "link", onclick: () => { s.groupIds = manifest.groups.map((g) => g.id); update(); } }, "すべて選ぶ"),
            h("button", { type: "button", class: "link", onclick: () => { s.groupIds = []; update(); } }, "すべて外す"))),
        groupList),
      h("div", { class: "field" }, h("h2", {}, "ペアの数"), pairList),
      h("div", { class: "field" }, h("h2", {}, "画像"), modeList),
      h("div", { class: "field" },
        h("h2", {}, "やさしさ"),
        h("label", { class: "toggle", for: "same" }, sameToggle,
          h("span", {}, "同じ写真どうしでペアにする", h("small", {}, "初心者向け。ふつうは同じ人の別の写真がペアになります")))),
      best, problem, start),
    h("footer", { class: "foot" },
      h("button", { type: "button", class: "link", onclick: opts.onCredits }, "画像のクレジット"),
      h("span", {}, `${manifest.members.length}人・${totalImages}枚`)),
    h("p", { class: "disclaimer" }, "非営利の非公式ファンメイドです。各アーティスト・所属事務所とは関係ありません。")));
  update();
}
