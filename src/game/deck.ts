/**
 * 山札を作る。
 *
 * ルール
 * - ペアは「同じ人物」の2枚。ふつうは同じ人物の**別の写真**を2枚使う(samePhoto なら同じ写真を2枚)
 * - 出題するメンバーより組数が多いときは、同じメンバーが2組以上出る(どの2枚を合わせてもペアになる)
 * - どのメンバーを出すかは MemberPicker で差し替えられる(後で「苦手克服モード」を足すための入口)
 */
import type { GameSettings, ImageMode, Manifest, ManifestImage, ManifestMember } from "../types";
import { type Rng, shuffle } from "./random";

export interface Card {
  /** 山札の中で一意 */
  uid: number;
  memberId: string;
  imageKey: string;
  src: string;
  credit: string;
}

export interface Deck {
  cards: Card[];
  /** 出題したメンバー(重複なし・出題順) */
  memberIds: string[];
  /** singleGroup のときに選ばれたグループ */
  groupId?: string;
}

/** 候補のメンバーから n 人を選ぶ。既定はランダム */
export type MemberPicker = (pool: ManifestMember[], n: number, rng: Rng) => ManifestMember[];

export const randomPicker: MemberPicker = (pool, n, rng) => shuffle(pool, rng).slice(0, n);

export class DeckError extends Error {}

/** そのメンバーで作れる組の最大数 */
export function pairCapacity(member: ManifestMember, samePhoto: boolean): number {
  return samePhoto ? member.images.length : Math.floor(member.images.length / 2);
}

/** メンバーの一覧で作れる組の最大数 */
export function maxPairs(members: ManifestMember[], samePhoto: boolean): number {
  return members.reduce((sum, m) => sum + pairCapacity(m, samePhoto), 0);
}

export function membersOf(manifest: Manifest, groupIds: readonly string[]): ManifestMember[] {
  const wanted = new Set(groupIds);
  return manifest.members.filter((m) => wanted.has(m.group) && m.images.length > 0);
}

/** この設定で遊べるか(遊べないときは理由を返す) */
export function checkSettings(manifest: Manifest, s: GameSettings): string | null {
  if (s.groupIds.length === 0) return "グループを1つ以上選んでください";
  if (s.singleGroup) {
    const ok = s.groupIds.some((g) => maxPairs(membersOf(manifest, [g]), s.samePhoto) >= s.pairs);
    return ok ? null : `${s.pairs}組を1つのグループだけで作れるグループがありません`;
  }
  const max = maxPairs(membersOf(manifest, s.groupIds), s.samePhoto);
  return max >= s.pairs ? null : `選んだグループでは最大 ${max} 組までです`;
}

/** 各メンバーに何組ずつ割り当てるか。まず1人1組ずつ、足りなければ写真に余裕のある人に追加する */
function allocate(members: ManifestMember[], pairs: number, samePhoto: boolean, rng: Rng): Map<ManifestMember, number> {
  const counts = new Map<ManifestMember, number>();
  let left = pairs;
  while (left > 0) {
    const room = members.filter((m) => (counts.get(m) ?? 0) < pairCapacity(m, samePhoto));
    if (room.length === 0) throw new DeckError("写真が足りません");
    // 割り当てが少ない人から順に(同じ人ばかりにならないように)
    const minCount = Math.min(...room.map((m) => counts.get(m) ?? 0));
    const next = shuffle(room.filter((m) => (counts.get(m) ?? 0) === minCount), rng);
    for (const m of next.slice(0, left)) {
      counts.set(m, (counts.get(m) ?? 0) + 1);
      left--;
    }
  }
  return counts;
}

export function buildDeck(
  manifest: Manifest,
  s: GameSettings,
  rng: Rng = Math.random,
  picker: MemberPicker = randomPicker,
): Deck {
  const problem = checkSettings(manifest, s);
  if (problem) throw new DeckError(problem);

  let groupId: string | undefined;
  let pool: ManifestMember[];
  if (s.singleGroup) {
    const candidates = s.groupIds.filter((g) => maxPairs(membersOf(manifest, [g]), s.samePhoto) >= s.pairs);
    groupId = shuffle(candidates, rng)[0];
    pool = membersOf(manifest, [groupId]);
  } else {
    pool = membersOf(manifest, s.groupIds);
  }

  // 組数がメンバー数以下なら picker で選んだ人を1組ずつ。多ければ全員を使って割り振る
  pool = pool.filter((m) => pairCapacity(m, s.samePhoto) > 0);
  const chosen = s.pairs <= pool.length ? picker(pool, s.pairs, rng) : pool;
  const counts = allocate(chosen, s.pairs, s.samePhoto, rng);

  let uid = 0;
  const cards: Card[] = [];
  const toCard = (m: ManifestMember, img: ManifestImage, mode: ImageMode): Card => ({
    uid: uid++, memberId: m.id, imageKey: img.key, src: img[mode], credit: img.credit,
  });
  for (const [member, n] of counts) {
    const photos = shuffle(member.images, rng);
    for (let i = 0; i < n; i++) {
      if (s.samePhoto) {
        cards.push(toCard(member, photos[i], s.mode), toCard(member, photos[i], s.mode));
      } else {
        cards.push(toCard(member, photos[2 * i], s.mode), toCard(member, photos[2 * i + 1], s.mode));
      }
    }
  }
  return {
    cards: shuffle(cards, rng),
    memberIds: [...counts.keys()].map((m) => m.id),
    groupId,
  };
}
