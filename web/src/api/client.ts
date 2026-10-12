import axios from "axios";
import type { AlbumDetail, Playlist, Song, SongUrlItem, ArtistDetail } from "./types";

/** 所有请求都走 nginx 的 /api/* → 增强服务（换源、AI、音频代理都在那边） */
const http = axios.create({ baseURL: "/api", timeout: 30000 });

http.interceptors.response.use(
  (r) => r,
  (e) => Promise.reject(e?.response?.data?.error ? new Error(e.response.data.error) : e),
);

/** 歌名去标点的小工具，用于「同名同歌手」匹配 */
export const norm = (s?: string) => (s || "").toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]+/g, "");

export const api = {
  async songDetail(ids: (number | string)[]): Promise<Song[]> {
    if (!ids.length) return [];
    const { data } = await http.get("/song/detail", { params: { ids: JSON.stringify(ids.slice(0, 1000)) } });
    return data.songs || [];
  },

  async songUrl(id: number | string): Promise<SongUrlItem | null> {
    const { data } = await http.get("/song/url", { params: { id } });
    return (data.data || [])[0] || null;
  },

  async lyric(id: number | string) {
    const { data } = await http.get("/lyric", { params: { id } });
    return { lyric: (data.lrc?.lyric || "") as string, tlyric: (data.tlyric?.lyric || "") as string };
  },

  async playlist(id: number | string): Promise<Playlist | null> {
    const { data } = await http.get("/playlist/detail", { params: { id } });
    return data.playlist || null;
  },

  /** 歌单全量歌曲（playlist/detail 只带前若干首） */
  async playlistTracks(id: number | string, limit = 1000, offset = 0): Promise<Song[]> {
    const { data } = await http.get("/playlist/track/all", { params: { id, limit, offset } });
    return data.songs || [];
  },

  async album(id: number | string): Promise<{ album: AlbumDetail | null; songs: Song[] }> {
    const { data } = await http.get("/album", { params: { id } });
    return { album: data.album || null, songs: data.songs || [] };
  },

  async artist(id: number | string): Promise<{ artist: ArtistDetail | null; hotSongs: Song[] }> {
    const { data } = await http.get("/artists", { params: { id } });
    return { artist: data.artist || null, hotSongs: data.hotSongs || [] };
  },

  async artistTopSongs(id: number | string): Promise<Song[]> {
    const { data } = await http.get("/artist/top/song", { params: { id } });
    return data.songs || [];
  },

  async artistAlbums(id: number | string, limit = 30) {
    const { data } = await http.get("/artist/album", { params: { id, limit } });
    return data.hotAlbums || [];
  },

  async search(keywords: string, type = 1, limit = 30, offset = 0) {
    const { data } = await http.get("/search", { params: { keywords, type, limit, offset } });
    const r = data.result || {};
    return { songs: r.songs || [], albums: r.albums || [], artists: r.artists || [], playlists: r.playlists || [] };
  },

  async personalized(limit = 12) {
    const { data } = await http.get("/personalized", { params: { limit } });
    return (data.result || []) as { id: number; name: string; picUrl: string; playCount?: number }[];
  },

  async newAlbums(limit = 12) {
    const { data } = await http.get("/album/new", { params: { limit } });
    return (data.albums || []) as { id: number; name: string; picUrl: string; artist?: { name: string } }[];
  },

  async toplists() {
    const { data } = await http.get("/toplist");
    return (data.list || []) as { id: number; name: string; coverImgUrl: string; updateFrequency?: string }[];
  },

  async topPlaylists(cat = "全部", limit = 24) {
    const { data } = await http.get("/top/playlist", { params: { cat, limit } });
    return (data.playlists || []) as Playlist[];
  },

  /** 匿名可用的歌单列表（接口默认账号） */
  async userPlaylists() {
    const { data } = await http.get("/user/playlist", { params: { uid: 32953014, limit: 30 } });
    return (data.playlist || []) as { id: number; name: string; coverImgUrl: string; trackCount?: number }[];
  },

  async dailySongs(): Promise<Song[]> {
    const { data } = await http.get("/recommend/songs");
    return data?.data?.dailySongs || [];
  },

  async personalFm(): Promise<Song[]> {
    const { data } = await http.get("/personal_fm");
    return data?.data || [];
  },

  /** AI：自然语言点歌 */
  async aiQuery(q: string, count = 5) {
    const { data } = await http.post("/ai/query", { q, count });
    return data as { reply: string; songs: Song[]; playable_count?: number; error?: string };
  },

  /** AI：无缝续播（基于当前曲目接着推） */
  async aiContinue(seedId: number | string, want = 6, exclude: (number | string)[] = []) {
    const { data } = await http.get("/ai/continue", {
      params: { sid: seedId, want, exclude: exclude.join(",") },
    });
    return data as { title: string; reply: string; songs: Song[]; error?: string };
  },

  /** AI：统一指令入口——一句话判断意图（点歌/电台/续播/控制） */
  async aiAsk(q: string, seed?: number | string, exclude: (number | string)[] = []) {
    const { data } = await http.post("/ai/ask", { q, seed: seed ? String(seed) : "", exclude });
    return data as {
      intent: "play" | "radio" | "continue" | "control" | "unknown";
      control?: string; reply?: string; title?: string; songs?: Song[];
      playable_count?: number; error?: string;
    };
  },

  /** AI：一句话生成电台/歌单 */
  async aiRadio(q: string, count = 15) {
    const { data } = await http.post("/ai/radio", { q, count });
    return data as { title: string; reply: string; songs: Song[]; playable_count?: number;
                     picked?: number; curated?: boolean; error?: string };
  },

  /** 口味上报：前端按真实收听行为上报，服务端据此让 AI 更懂你 */
  /** 服务端收藏列表（跨设备/供 AI 使用） */
  async favorites() {
    const { data } = await http.get("/favorites");
    return (data.favorites || []) as { id: string; name: string; artist: string; liked_at: number }[];
  },

  /** 批量预热：把这批歌提前落到服务器本地盘（点下去立刻响） */
  async warmup(ids: (number | string)[]) {
    const { data } = await http.post("/warmup", { ids });
    return data as { ok: boolean; accepted: number; cached: number };
  },

  /** 播放失败一键诊断（第 4 项优化）：只探测不落盘，返回明确原因 */
  async diag(id: number | string) {
    const { data } = await http.get("/client-diag", { params: { id } });
    return data as {
      verdict: string; reason: string; cached: boolean;
      name?: string; artist?: string;
      sources_tried?: { source: string; ok: boolean; note: string }[];
    };
  },

  reportTaste(songId: number | string, action: "play" | "skip", played: number, dur: number) {
    return http.post("/client-report", { kind: "taste", id: String(songId), action, played, dur })
      .catch(() => void 0);
  },
};
