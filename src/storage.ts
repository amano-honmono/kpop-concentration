/**
 * localStorage への保存(ベスト記録・前回の設定・取り違えの記録)。
 * プライベートブラウズなどで localStorage が使えなくても、ゲームは動くようにする。
 */
import type { Mistake } from "./game/engine";
import type { GameSettings } from "./types";

const PREFIX = "kpop-concentration:v1:";

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function save(key: string, value: unknown): void {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // 保存できなくても遊べる
  }
}

// ---------------------------------------------------------------- 設定

export function loadSettings(): Partial<GameSettings> {
  return load<Partial<GameSettings>>("settings", {});
}

export function saveSettings(s: GameSettings): void {
  save("settings", s);
}

// ---------------------------------------------------------------- ベスト記録

export interface Record {
  timeMs: number;
  moves: number;
  misses: number;
  date: string;
}

export interface BestRecords {
  fastest?: Record;
  fewestMoves?: Record;
}

/** 記録は「グループ・組数・画像モード・難易度」が同じゲームどうしで比べる */
export function recordKey(s: GameSettings): string {
  const groups = [...s.groupIds].sort().join(",");
  return [groups, s.singleGroup ? "single" : "mixed", s.pairs, s.mode, s.samePhoto ? "same" : "diff"].join("|");
}

export function loadBest(s: GameSettings): BestRecords {
  return load<{ [k: string]: BestRecords }>("best", {})[recordKey(s)] ?? {};
}

/** 記録を保存し、更新した項目を返す */
export function submitRecord(s: GameSettings, r: Record): { fastest: boolean; fewestMoves: boolean; previous: BestRecords } {
  const all = load<{ [k: string]: BestRecords }>("best", {});
  const key = recordKey(s);
  const previous = all[key] ?? {};
  const fastest = !previous.fastest || r.timeMs < previous.fastest.timeMs;
  const fewestMoves = !previous.fewestMoves || r.moves < previous.fewestMoves.moves
    || (r.moves === previous.fewestMoves.moves && r.timeMs < previous.fewestMoves.timeMs);
  all[key] = {
    fastest: fastest ? r : previous.fastest,
    fewestMoves: fewestMoves ? r : previous.fewestMoves,
  };
  save("best", all);
  return { fastest, fewestMoves, previous };
}

// ---------------------------------------------------------------- 取り違えの記録(苦手克服モード用)

/** "メンバーA|メンバーB"(ID の辞書順)→ 取り違えた回数 */
export type ConfusionStats = { [pair: string]: number };

export function pairKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

export function loadConfusions(): ConfusionStats {
  return load<ConfusionStats>("confusions", {});
}

export function recordMistakes(mistakes: readonly Mistake[]): void {
  if (mistakes.length === 0) return;
  const stats = loadConfusions();
  for (const m of mistakes) {
    const k = pairKey(m.a, m.b);
    stats[k] = (stats[k] ?? 0) + 1;
  }
  save("confusions", stats);
}
