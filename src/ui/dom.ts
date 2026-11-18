type Attrs = { [key: string]: string | number | boolean | null | undefined | ((ev: Event) => void) };
type Child = Node | string | number | null | undefined | false;

/** 小さな DOM 作成ヘルパー。on* は addEventListener、class は className、false/null の属性は付けない */
export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: (Child | Child[])[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (typeof v === "function") el.addEventListener(k.replace(/^on/, "").toLowerCase(), v);
    else if (k === "class") el.className = String(v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : String(c));
  }
  return el;
}

export function formatTime(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function asset(path: string): string {
  return import.meta.env.BASE_URL + path;
}

/** 画像を先に読み込んでおく(めくったときに真っ白にならないように) */
export function preload(urls: string[], onProgress?: (done: number, total: number) => void): Promise<void> {
  let done = 0;
  const unique = [...new Set(urls)];
  return Promise.all(unique.map((url) => new Promise<void>((resolve) => {
    const img = new Image();
    img.onload = img.onerror = () => {
      done++;
      onProgress?.(done, unique.length);
      resolve();
    };
    img.src = url;
  }))).then(() => undefined);
}
