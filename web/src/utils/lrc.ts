export interface LyricLine { t: number; text: string; tr?: string }

/** 解析 LRC：支持一行多时间戳、毫秒/百分秒、以及双语歌词（tlyric 合并到同一时间轴） */
export function parseLrc(lrc: string, tlyric = ""): LyricLine[] {
  const map = new Map<number, LyricLine>();
  const add = (src: string, key: "text" | "tr") => {
    for (const raw of (src || "").split("\n")) {
      const times = [...raw.matchAll(/\[(\d{1,2}):(\d{2})(?:[.:](\d{1,3}))?\]/g)];
      if (!times.length) continue;
      const text = raw.replace(/\[[^\]]*\]/g, "").trim();
      if (!text) continue;
      for (const m of times) {
        const t = Number(m[1]) * 60 + Number(m[2]) + (m[3] ? Number(`0.${m[3]}`) : 0);
        const cur = map.get(t) || { t, text: "" };
        cur[key] = text;
        map.set(t, cur);
      }
    }
  };
  add(lrc, "text");
  if (tlyric) add(tlyric, "tr");
  return [...map.values()].sort((a, b) => a.t - b.t);
}

/** 返回当前时间对应的歌词行下标（最后一条 t <= cur） */
export function activeLine(lines: LyricLine[], cur: number): number {
  if (!lines.length) return -1;
  let lo = 0, hi = lines.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (lines[mid].t <= cur + 0.2) { ans = mid; lo = mid + 1; } else { hi = mid - 1; }
  }
  return ans;
}
