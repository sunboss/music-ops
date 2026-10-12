import type { Song } from "@/api/types";

const KEY = "playHistory";
export interface HistoryItem {
  id: number; name: string; artist: string; pic?: string; albumId?: number; ts: number;
}

/** 记录一次播放（本地，最多 300 条，去重后按时间倒序） */
export function pushHistory(song: Song) {
  try {
    const list: HistoryItem[] = JSON.parse(localStorage.getItem(KEY) || "[]");
    const item: HistoryItem = {
      id: song.id,
      name: song.name,
      artist: (song.ar || []).map((a) => a.name).join(", "),
      pic: song.al?.picUrl,
      albumId: song.al?.id,
      ts: Date.now(),
    };
    const next = [item, ...list.filter((x) => x.id !== song.id)].slice(0, 300);
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch { /* 隐私模式下 localStorage 可能不可用，忽略 */ }
}

export function readHistory(): HistoryItem[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

export function clearHistory() {
  try { localStorage.removeItem(KEY); } catch { /* noop */ }
}
