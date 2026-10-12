/**
 * 收藏（我喜欢）。
 *
 * 双重作用：① 界面功能；② **喂给服务端的口味记忆** ——
 * 明确收藏比"听满 30 秒"强得多，服务端会把它放在 AI 提示词最前面，
 * 于是「按我的收藏生成电台」才会真的像你。
 * 本地存一份保证点击即时生效，同时 fire-and-forget 上报给服务端。
 */
import type { Song } from "@/api/types";

export interface FavItem {
  id: number;
  name: string;
  artist: string;
  pic?: string;
  at: number;
}

const KEY = "rm-favorites";
const MAX = 800;

export function readFavs(): FavItem[] {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
    return Array.isArray(raw) ? (raw as FavItem[]) : [];
  } catch {
    return [];
  }
}

function write(list: FavItem[]) {
  localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)));
}

export function isFav(id: number | string | undefined): boolean {
  if (!id) return false;
  return readFavs().some((x) => String(x.id) === String(id));
}

function report(id: number | string, on: boolean) {
  // 与 play/skip 走同一个口味通道；失败不影响界面
  fetch("/api/client-report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "taste", id: String(id), action: on ? "like" : "unlike" }),
  }).catch(() => {});
}

/** 切换收藏，返回切换后的状态 */
export function toggleFav(song: Song | undefined): boolean {
  if (!song?.id) return false;
  const list = readFavs();
  const hit = list.findIndex((x) => String(x.id) === String(song.id));
  if (hit >= 0) {
    list.splice(hit, 1);
    write(list);
    report(song.id, false);
    return false;
  }
  list.unshift({
    id: song.id,
    name: song.name || "",
    artist: (song.ar || []).map((a) => a.name).join("、"),
    pic: song.al?.picUrl || "",
    at: Date.now(),
  });
  write(list);
  report(song.id, true);
  return true;
}

/** 收藏项还原成可播放的歌曲对象（时长等信息播放时再补全） */
export function favSongs(): Song[] {
  return readFavs().map((f) => ({
    id: f.id,
    name: f.name,
    dt: 0,
    ar: [{ id: 0, name: f.artist }],
    al: { id: 0, name: "", picUrl: f.pic },
  } as Song));
}
