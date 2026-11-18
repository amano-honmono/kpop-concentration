/** public/cards/manifest.json の形(画像パイプラインの build.py が書き出す) */

export type Lang = "ja" | "en" | "ko";
export type LocalizedName = Record<Lang, string>;
export type ImageMode = "full" | "face";

export interface ManifestImage {
  key: string;
  full: string;
  face: string;
  /** credits のキー */
  credit: string;
}

export interface ManifestMember {
  /** カードID(例: twice-nayeon) */
  id: string;
  group: string;
  name: LocalizedName;
  images: ManifestImage[];
}

export interface ManifestGroup {
  id: string;
  name: LocalizedName;
  aliases?: string[];
  members: string[];
}

export interface Credit {
  title: string;
  author: string;
  license: string;
  licenseUrl: string;
  sourceUrl: string;
  source: "commons" | "manual";
  modified: string;
}

export interface Manifest {
  version: number;
  generatedAt: string;
  groups: ManifestGroup[];
  members: ManifestMember[];
  credits: Record<string, Credit>;
}

export interface GameSettings {
  groupIds: string[];
  /** 選んだグループのうち1つだけから出題する(難しい) */
  singleGroup: boolean;
  pairs: number;
  mode: ImageMode;
  /** ペアの2枚に同じ写真を使う(初心者向け) */
  samePhoto: boolean;
}

export const PAIR_OPTIONS = [6, 8, 12, 18] as const;
