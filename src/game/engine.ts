/**
 * 神経衰弱の進行(画面から独立したロジック)。
 *
 * - 2枚めくって同じ人物ならペア成立。違えばミスとして、少し見せてから裏に戻す
 * - 手数(2枚めくった回数)・ミス・経過時間を数える
 * - プレイヤーは配列で持つ(今は1人。2人対戦はミスで手番を交代するだけで足せる)
 */
import type { Card, Deck } from "./deck";

export type CardState = "down" | "up" | "matched";

export interface Player {
  name: string;
  pairs: number;
}

export type GameEvent =
  | { type: "flip"; card: Card }
  | { type: "match"; cards: [Card, Card]; player: number }
  | { type: "miss"; cards: [Card, Card]; player: number }
  | { type: "hide"; cards: [Card, Card] }
  | { type: "turn"; player: number }
  | { type: "clear" };

export interface Mistake {
  a: string;
  b: string;
}

export class Game {
  readonly cards: Card[];
  readonly state = new Map<number, CardState>();
  readonly players: Player[];
  readonly mistakes: Mistake[] = [];
  current = 0;
  moves = 0;
  misses = 0;
  startedAt: number | null = null;
  endedAt: number | null = null;

  private open: Card[] = [];
  /** ミスした2枚を表にしている間は true */
  private pendingMiss: [Card, Card] | null = null;
  private listeners: ((e: GameEvent) => void)[] = [];

  constructor(readonly deck: Deck, playerNames: string[] = ["あなた"], private now: () => number = Date.now) {
    this.cards = deck.cards;
    for (const c of this.cards) this.state.set(c.uid, "down");
    this.players = playerNames.map((name) => ({ name, pairs: 0 }));
  }

  get totalPairs(): number {
    return this.cards.length / 2;
  }

  get matchedPairs(): number {
    return this.players.reduce((s, p) => s + p.pairs, 0);
  }

  get finished(): boolean {
    return this.endedAt !== null;
  }

  get busy(): boolean {
    return this.pendingMiss !== null;
  }

  elapsedMs(): number {
    if (this.startedAt === null) return 0;
    return (this.endedAt ?? this.now()) - this.startedAt;
  }

  on(fn: (e: GameEvent) => void): () => void {
    this.listeners.push(fn);
    return () => {
      this.listeners = this.listeners.filter((l) => l !== fn);
    };
  }

  private emit(e: GameEvent): void {
    for (const l of this.listeners) l(e);
  }

  /** カードをめくる。めくれなかったら false */
  flip(uid: number): boolean {
    if (this.finished) return false;
    const card = this.cards.find((c) => c.uid === uid);
    if (!card) return false;
    // ミスした2枚を見せている途中なら、すぐ裏に戻してから続ける
    // (見せている2枚のどちらかを押したときは、裏に戻したうえでそのカードをめくり直す)
    if (this.pendingMiss) this.hideMiss();
    if (this.state.get(uid) !== "down") return false;

    if (this.startedAt === null) this.startedAt = this.now();
    this.state.set(uid, "up");
    this.open.push(card);
    this.emit({ type: "flip", card });

    if (this.open.length === 2) {
      const [a, b] = this.open;
      this.open = [];
      this.moves++;
      if (a.memberId === b.memberId) {
        this.state.set(a.uid, "matched");
        this.state.set(b.uid, "matched");
        this.players[this.current].pairs++;
        this.emit({ type: "match", cards: [a, b], player: this.current });
        if (this.matchedPairs === this.totalPairs) {
          this.endedAt = this.now();
          this.emit({ type: "clear" });
        }
      } else {
        this.misses++;
        this.mistakes.push({ a: a.memberId, b: b.memberId });
        this.pendingMiss = [a, b];
        this.emit({ type: "miss", cards: [a, b], player: this.current });
      }
    }
    return true;
  }

  /** ミスした2枚を裏に戻す(画面側がタイマーで呼ぶ。次のカードをめくったときも呼ばれる) */
  hideMiss(): void {
    if (!this.pendingMiss) return;
    const cards = this.pendingMiss;
    this.pendingMiss = null;
    for (const c of cards) this.state.set(c.uid, "down");
    this.emit({ type: "hide", cards });
    if (this.players.length > 1) {
      this.current = (this.current + 1) % this.players.length;
      this.emit({ type: "turn", player: this.current });
    }
  }
}
