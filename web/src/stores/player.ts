import { defineStore } from "pinia";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import { parseLrc, type LyricLine } from "@/utils/lrc";
import { pushHistory } from "@/utils/history";

/**
 * 播放器内核：全局单例的原生 <audio>，路由切换绝不重建。
 * 说明：之前用 Howler，但它无法从 /api/audio/proxy?id=X 这种没有扩展名的地址推断格式
 * （"No file extension was found"），会直接加载失败；原生元素只看 Content-Type，更稳，
 * 也省掉 36KB 依赖。
 */
const el: HTMLAudioElement = new Audio();
el.preload = "metadata";
let playStart = 0;
let reported = false;

export const usePlayerStore = defineStore("player", {
  state: () => ({
    queue: [] as Song[],
    index: -1,
    playing: false,
    loading: false,
    progress: 0,
    duration: 0,
    volume: Number(localStorage.getItem("volume") ?? 1),
    error: "",
    showFull: false,
    lyrics: [] as LyricLine[],
    lyricFor: -1,
    ready: false,
  }),
  getters: {
    current(state): Song | null { return state.queue[state.index] ?? null; },
    hasQueue(state) { return state.queue.length > 0; },
  },
  actions: {
    /** 绑定一次性事件（单例，只绑一次） */
    init() {
      if (this.ready) return;
      this.ready = true;
      el.volume = this.volume;

      el.addEventListener("loadedmetadata", () => {
        this.loading = false;
        if (isFinite(el.duration) && el.duration > 0) this.duration = Math.round(el.duration);
      });
      el.addEventListener("timeupdate", () => {
        this.progress = el.currentTime || 0;
        // 听满 30 秒立即记账：不能只在切歌时上报，否则一直听下去永远不落库
        if (!reported && playStart && Date.now() - playStart >= 30000 && this.current) {
          reported = true;
          void api.reportTaste(this.current.id, "play", Math.round(this.progress), this.duration);
        }
      });
      el.addEventListener("play", () => { this.playing = true; playStart = playStart || Date.now(); });
      el.addEventListener("pause", () => { this.playing = false; });
      el.addEventListener("ended", () => {
        if (!reported && this.current) {
          reported = true;
          void api.reportTaste(this.current.id, "play", Math.round(el.duration || 0), this.duration);
        }
        this.next(true);
      });
      el.addEventListener("error", () => {
        this.loading = false;
        this.error = "这首歌加载失败";
        const deadIndex = this.index;
        if (deadIndex >= 0 && this.queue[deadIndex]) this.queue[deadIndex].playable = false;
      });
      this.setupMediaSession();
    },

    /** 锁屏/通知栏控制（手机上是刚需） */
    setupMediaSession() {
      if (!("mediaSession" in navigator)) return;
      const ms = navigator.mediaSession;
      ms.setActionHandler("play", () => this.toggle());
      ms.setActionHandler("pause", () => this.toggle());
      ms.setActionHandler("previoustrack", () => this.prev());
      ms.setActionHandler("nexttrack", () => this.next());
    },

    syncMediaSession() {
      if (!("mediaSession" in navigator) || !this.current) return;
      const s = this.current;
      try {
        navigator.mediaSession.metadata = new MediaMetadata({
          title: s.name,
          artist: (s.ar || []).map((a) => a.name).join(", "),
          album: s.al?.name || "",
          artwork: s.al?.picUrl ? [{ src: s.al.picUrl, sizes: "500x500", type: "image/jpeg" }] : [],
        });
      } catch { /* 部分浏览器不支持完整 metadata，忽略 */ }
    },

    playQueue(songs: Song[], index = 0) {
      if (!songs.length) return;
      this.queue = songs.slice();
      void this.playAt(index);
    },

    async playAt(i: number) {
      this.init();
      const song = this.queue[i];
      if (!song) return;
      // 上一首没听够就算「跳过」（服务端据此不再推荐）
      if (playStart && !reported && Date.now() - playStart < 20000) {
        const prev = this.queue[this.index];
        const played = Math.round((Date.now() - playStart) / 1000);
        if (prev && prev.id !== song.id) void api.reportTaste(prev.id, "skip", played, Math.round(this.duration || 0));
      }
      this.index = i;
      this.loading = true;
      this.error = "";
      this.progress = 0;
      reported = false;
      this.syncMediaSession();
      void this.loadLyrics();

      try {
        const item = await api.songUrl(song.id);
        if (!item?.url || item.source === "no-source") {
          song.playable = false;
          this.loading = false;
          if (i + 1 < this.queue.length) { void this.playAt(i + 1); }
          else this.error = "后面没有可播放的歌了";
          return;
        }
        song.playable = true;
        pushHistory(song);                       // 本地播放历史（音乐库/离线可见）
        this.duration = Math.round((song.dt || 0) / 1000);
        el.src = item.url;
        playStart = Date.now();
        await el.play().catch(() => { this.loading = false; });
        this.loading = false;
      } catch {
        this.loading = false;
        this.error = "取源失败";
      }
    },

    toggle() {
      this.init();
      if (!el.src) { if (this.queue.length) void this.playAt(Math.max(0, this.index)); return; }
      if (el.paused) { playStart = playStart || Date.now(); void el.play().catch(() => {}); }
      else el.pause();
    },

    next(fromEnd = false) {
      if (this.index + 1 < this.queue.length) { void this.playAt(this.index + 1); return; }
      el.pause(); this.progress = 0;
      if (!fromEnd && this.queue.length) void this.playAt(0);
      else this.playing = false;
    },

    prev() {
      if (this.progress > 4) { el.currentTime = 0; return; }   // 播过 4 秒则回到本首开头
      if (this.index > 0) void this.playAt(this.index - 1);
    },

    seekRatio(r: number) {
      if (!this.duration) return;
      const t = Math.max(0, Math.min(1, r)) * this.duration;
      try { el.currentTime = t; } catch { /* 元数据未就绪时忽略 */ }
      this.progress = t;
    },

    setVolume(v: number) {
      this.volume = v;
      el.volume = v;
      localStorage.setItem("volume", String(v));
    },

    async loadLyrics() {
      const s = this.current;
      if (!s) { this.lyrics = []; this.lyricFor = -1; return; }
      if (this.lyricFor === s.id) return;
      this.lyricFor = s.id;
      this.lyrics = [];
      try {
        const r = await api.lyric(s.id);
        if (this.lyricFor !== s.id) return;
        this.lyrics = parseLrc(r.lyric, r.tlyric);
      } catch { /* 拿不到歌词就留空，不打扰播放 */ }
    },
  },
});
