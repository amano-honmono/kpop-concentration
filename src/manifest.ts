import type { Manifest, ManifestGroup, ManifestMember } from "./types";
import { asset } from "./ui/dom";

export class ManifestError extends Error {}

export async function loadManifest(): Promise<Manifest> {
  let res: Response;
  try {
    res = await fetch(asset("cards/manifest.json"), { cache: "no-cache" });
  } catch {
    throw new ManifestError("manifest.json を読み込めませんでした");
  }
  if (!res.ok) throw new ManifestError("public/cards/manifest.json がありません");
  const m = (await res.json()) as Manifest;
  if (!m.members?.length) throw new ManifestError("manifest.json にメンバーが入っていません");
  return m;
}

/** 名前の表示などで使う索引 */
export class Catalog {
  readonly members = new Map<string, ManifestMember>();
  readonly groups = new Map<string, ManifestGroup>();

  constructor(readonly manifest: Manifest) {
    for (const m of manifest.members) this.members.set(m.id, m);
    for (const g of manifest.groups) this.groups.set(g.id, g);
  }

  member(id: string): ManifestMember {
    const m = this.members.get(id);
    if (!m) throw new Error(`unknown member ${id}`);
    return m;
  }

  groupName(groupId: string): string {
    return this.groups.get(groupId)?.name.en ?? groupId;
  }
}
