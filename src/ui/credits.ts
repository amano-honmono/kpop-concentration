import type { Catalog } from "../manifest";
import { asset, h } from "./dom";

export function renderCredits(root: HTMLElement, catalog: Catalog, onBack: () => void): void {
  const { manifest } = catalog;
  const link = (href: string, text: string) =>
    href ? h("a", { href, target: "_blank", rel: "noopener noreferrer" }, text) : text;

  const sections = manifest.groups.map((g) => h("section", { class: "credit-group" },
    h("h2", {}, g.name.en),
    ...g.members.map((id) => {
      const m = catalog.member(id);
      return h("div", { class: "credit-member" },
        h("h3", {}, m.name.ja, h("small", {}, ` ${m.name.en} / ${m.name.ko}`)),
        h("ul", {}, m.images.map((img) => {
          const c = manifest.credits[img.credit];
          return h("li", { class: "credit" },
            h("img", { src: asset(img.full), alt: "", loading: "lazy" }),
            h("span", {},
              link(c?.sourceUrl ?? "", c?.title.replace(/^File:/, "") ?? img.key), h("br"),
              h("small", {}, "作者: ", c?.author ?? "不明", " · ライセンス: ", link(c?.licenseUrl ?? "", c?.license ?? "不明"),
                c?.modified ? ` · 加工: ${c.modified}` : "")));
        })));
    })));

  root.replaceChildren(h("div", { class: "screen credits" },
    h("header", { class: "credits-head" },
      h("button", { type: "button", class: "btn ghost small", onclick: onBack }, "戻る"),
      h("h1", {}, "画像のクレジット")),
    h("section", { class: "panel note" },
      h("p", {}, "カードの写真は ", link("https://commons.wikimedia.org/", "Wikimedia Commons"),
        " から、CC BY・CC BY-SA・パブリックドメインなど、利用条件が明記されたものだけを使っています。"),
      h("p", {}, "すべての写真に、切り抜き・回転・拡大縮小・背景除去の加工をしています。",
        "加工した写真は、それぞれ元の写真と同じライセンスで公開しています。元の写真は各リンク先で見られます。"),
      h("p", {}, "グループとメンバーの情報は ", link("https://www.wikidata.org/", "Wikidata"), "(CC0)をもとにしています。"),
      h("p", {}, "このゲームは非営利の非公式ファンメイドで、各アーティスト・所属事務所とは関係ありません。")),
    ...sections));
}
