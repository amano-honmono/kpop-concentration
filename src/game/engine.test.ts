import { describe, expect, it } from "vitest";
import type { Card, Deck } from "./deck";
import { Game, type GameEvent } from "./engine";

function card(uid: number, memberId: string): Card {
  return { uid, memberId, imageKey: `${memberId}-${uid}`, src: "", credit: "" };
}

// A A B B の4枚
function deck(): Deck {
  return { cards: [card(0, "A"), card(1, "B"), card(2, "A"), card(3, "B")], memberIds: ["A", "B"] };
}

function setup(players?: string[]) {
  let t = 1000;
  const game = new Game(deck(), players, () => t);
  const events: GameEvent["type"][] = [];
  game.on((e) => events.push(e.type));
  return { game, events, tick: (ms: number) => { t += ms; } };
}

describe("Game", () => {
  it("同じ人物の2枚でペアが成立し、全部そろうとクリア", () => {
    const { game, events, tick } = setup();
    game.flip(0);
    tick(500);
    game.flip(2);
    expect(game.state.get(0)).toBe("matched");
    expect(game.moves).toBe(1);
    game.flip(1);
    game.flip(3);
    tick(1500);
    expect(game.finished).toBe(true);
    expect(game.elapsedMs()).toBe(500);
    expect(events).toEqual(["flip", "flip", "match", "flip", "flip", "match", "clear"]);
  });

  it("違う人物ならミスになり、hideMiss で裏に戻る", () => {
    const { game } = setup();
    game.flip(0);
    game.flip(1);
    expect(game.misses).toBe(1);
    expect(game.busy).toBe(true);
    expect(game.mistakes).toEqual([{ a: "A", b: "B" }]);
    game.hideMiss();
    expect(game.state.get(0)).toBe("down");
    expect(game.state.get(1)).toBe("down");
  });

  it("ミスを見せている間に次をめくると、先に裏に戻してからめくる", () => {
    const { game } = setup();
    game.flip(0);
    game.flip(1);
    expect(game.flip(2)).toBe(true);
    expect(game.state.get(0)).toBe("down");
    expect(game.state.get(2)).toBe("up");
  });

  it("ミスを見せている2枚のどちらかを押すと、そのカードを1枚目としてめくり直す", () => {
    const { game } = setup();
    game.flip(0);
    game.flip(1);
    expect(game.flip(0)).toBe(true);
    expect(game.state.get(0)).toBe("up");
    expect(game.state.get(1)).toBe("down");
    game.flip(2);
    expect(game.state.get(0)).toBe("matched");
    expect(game.misses).toBe(1);
  });

  it("表のカードやそろったカードはめくれない", () => {
    const { game } = setup();
    game.flip(0);
    expect(game.flip(0)).toBe(false);
    game.flip(2);
    expect(game.flip(2)).toBe(false);
    expect(game.moves).toBe(1);
  });

  it("2人で遊ぶときはミスで手番が替わる", () => {
    const { game } = setup(["P1", "P2"]);
    game.flip(0);
    game.flip(1);
    game.hideMiss();
    expect(game.current).toBe(1);
    game.flip(0);
    game.flip(2);
    expect(game.players[1].pairs).toBe(1);
    expect(game.current).toBe(1); // そろえたら続けてめくれる
  });
});
