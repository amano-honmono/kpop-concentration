import { describe, expect, it } from "vitest";
import type { GameSettings, Manifest, ManifestMember } from "../types";
import { buildDeck, checkSettings, DeckError, maxPairs } from "./deck";
import { seededRng } from "./random";

function member(id: string, group: string, photos: number): ManifestMember {
  return {
    id, group, name: { ja: id, en: id, ko: id },
    images: Array.from({ length: photos }, (_, i) => ({
      key: `${id}-${i}`, full: `cards/${id}/${i + 1}_full.webp`, face: `cards/${id}/${i + 1}_face.webp`, credit: `${id}/${i}`,
    })),
  };
}

function manifest(): Manifest {
  const members = [
    ...["a1", "a2", "a3", "a4"].map((id) => member(id, "A", 5)),
    ...["b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9"].map((id) => member(id, "B", 5)),
    member("c1", "C", 2), member("c2", "C", 3),
  ];
  const groups = ["A", "B", "C"].map((g) => ({
    id: g, name: { ja: g, en: g, ko: g }, members: members.filter((m) => m.group === g).map((m) => m.id),
  }));
  return { version: 1, generatedAt: "", groups, members, credits: {} };
}

const base: GameSettings = { groupIds: ["A", "B", "C"], singleGroup: false, pairs: 8, mode: "full", samePhoto: false };

function pairsOf(cards: { memberId: string; imageKey: string }[]) {
  const byMember = new Map<string, string[]>();
  for (const c of cards) byMember.set(c.memberId, [...(byMember.get(c.memberId) ?? []), c.imageKey]);
  return byMember;
}

describe("buildDeck", () => {
  it("ペアの2枚は同じ人物の別の写真になる", () => {
    for (let seed = 1; seed <= 50; seed++) {
      const deck = buildDeck(manifest(), base, seededRng(seed));
      expect(deck.cards).toHaveLength(16);
      for (const [, keys] of pairsOf(deck.cards)) {
        expect(keys.length % 2).toBe(0);
        expect(new Set(keys).size).toBe(keys.length); // 同じ写真は2回出ない
      }
    }
  });

  it("samePhoto なら同じ写真を2枚使う", () => {
    const deck = buildDeck(manifest(), { ...base, samePhoto: true }, seededRng(3));
    for (const [, keys] of pairsOf(deck.cards)) {
      expect(keys.length).toBe(2);
      expect(keys[0]).toBe(keys[1]);
    }
  });

  it("画像モードに合わせたパスを使う", () => {
    const deck = buildDeck(manifest(), { ...base, mode: "face" }, seededRng(4));
    expect(deck.cards.every((c) => c.src.endsWith("_face.webp"))).toBe(true);
  });

  it("選んだグループのメンバーだけが出る", () => {
    const deck = buildDeck(manifest(), { ...base, groupIds: ["B"], pairs: 6 }, seededRng(5));
    expect(deck.cards.every((c) => c.memberId.startsWith("b"))).toBe(true);
    expect(new Set(deck.memberIds).size).toBe(6);
  });

  it("メンバーより組数が多いときは、写真に余裕のある人が2組出る", () => {
    // グループ A は4人×5枚 → 1人2組まで、最大8組
    const deck = buildDeck(manifest(), { ...base, groupIds: ["A"], pairs: 8 }, seededRng(6));
    expect(deck.cards).toHaveLength(16);
    for (const [, keys] of pairsOf(deck.cards)) {
      expect(keys).toHaveLength(4);
      expect(new Set(keys).size).toBe(4);
    }
  });

  it("singleGroup では1つのグループだけから出る", () => {
    for (let seed = 1; seed <= 20; seed++) {
      const deck = buildDeck(manifest(), { ...base, singleGroup: true, pairs: 8 }, seededRng(seed));
      const groups = new Set(deck.cards.map((c) => c.memberId[0]));
      expect(groups.size).toBe(1);
      expect(deck.groupId).toBeDefined();
    }
  });

  it("作れない組数はエラーになる", () => {
    expect(maxPairs(manifest().members.filter((m) => m.group === "C"), false)).toBe(2);
    expect(checkSettings(manifest(), { ...base, groupIds: ["C"], pairs: 6 })).toMatch(/最大 2 組/);
    expect(() => buildDeck(manifest(), { ...base, groupIds: ["C"], pairs: 6 })).toThrow(DeckError);
    expect(checkSettings(manifest(), { ...base, groupIds: [] })).not.toBeNull();
  });
});
