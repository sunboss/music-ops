import { defineStore } from "pinia";
import { Howl } from "howler";
import { api } from "@/api/client";
import type { Song } from "@/api/types";

/** 播放器全局单例：路由切换绝不重建，保证不打断播放 */
let howl: Howl | null = null;
let playStart = 0;          // 本首开始播放的时间戳
let reported = false;       // 本首是否已上报过

export const usePlayerStore = defineStore("player", {
  state: () => ({
    queue: [] as Song[],
    index: -1,
    playing: false,
    loading: false,
    progress: 0,            // 秒
    duration: 0,            // 秒
    volume: 1,
    muted: false,
    error: "",
  }),
  getters: {
    current(state): Song | null { return state.queue[state.index] ?? null; },
    hasQueue(state) { return state.queue.length > 0; },
  },
  actions: {
    /** 播放一批歌（歌单/专辑/搜索结果是数组） */
    playQueue(songs: Song[], index = 0) {
      if (!songs.length) return;
      this.queue = songs.slice();
      this.playAt(index);
    },

    async playAt(i: number) {
      const song = this.queue[i];
      if (!song) return;
      this.index = i;
      this.loading = true;
      this.error = "";
      this.progress = 0;
      reported = false;

      // 上一首没听够就算「跳过」（服务端据此不再推荐）
      if (howl && playStart && !reported && Date.now() - playStart < 20000) {
        const prev = this.queue[this.index - 1];
        const played = Math.round((Date.now() - playStart) / 1000);
        if (prev) void api.reportTaste(prev.id, "skip", played, Math.round(this.duration || 0));
      }
      this.unload();

      try {
        const item = await api.songUrl(song.id);
        if (!item?.url || item.source === "no-source") {
          // 没有完整音源：标记置灰并自动跳到下一首（绝不静默播 30 秒试听）
          song.playable = false;
          const failed = i;
          this.loading = false;
          if (failed + 1 < this.queue.length) this.playAt(failed + 1);
          else this.error = "后面没有可播放的歌了";
          return;
        }
        song.playable = true;
        this.duration = Math.round((song.dt || 0) / 1000);
        const h = new Howl({
          src: [item.url],
          html5: true,
          volume: this.muted ? 0 : this.volume,
          onload: () => {
            this.loading = false;
            const d = h.duration();
            if (d && isFinite(d)) this.duration = Math.round(d);
          },
          onplay: () => {
            this.playing = true;
            playStart = playStart || Date.now();
          },
          onend: () => {
            if (!reported && this.current) {
              reported = true;
              void api.reportTaste(this.current.id, "play", Math.round(h.duration()), Math.round(h.duration()));
            }
            this.next(true);
          },
          onloaderror: () => { this.loading = false; this.error = "这首歌加载失败"; },
        });
        howl = h;
        playStart = Date.now();
        h.play();
        this.startTicker();
      } catch {
        this.loading = false;
        this.error = "取源失败";
      }
    },

    unload() {
      if (howl) { try { howl.unload(); } catch { /* noop */ } howl = null; }
      this.playing = false;
    },

    toggle() {
      if (!howl) { if (this.queue.length) this.playAt(Math.max(0, this.index)); return; }
      if (howl.playing()) howl.pause(); else howl.play();
      this.playing = !this.playing;
    },

    next(fromEnd = false) {
      if (this.index + 1 < this.queue.length) this.playAt(this.index + 1);
      else { this.unload(); this.progress = 0; if (!fromEnd) this.playAt(0); }
    },

    prev() {
      if (this.progress > 4 && howl) { howl.seek(0); return; }   // 播过 4 秒则回到本首开头
      if (this.index > 0) this.playAt(this.index - 1);
    },

    seekRatio(r: number) {
      if (!howl || !this.duration) return;
      const t = Math.max(0, Math.min(1, r)) * this.duration;
      howl.seek(t);
      this.progress = t;
    },

    setVolume(v: number) {
      this.volume = v;
      this.muted = v === 0;
      howl?.volume(v);
    },

    startTicker() {
      if ((this as unknown as { _t?: number })._t) return;
      const t = window.setInterval(() => {
        if (howl && howl.playing()) {
          const p = howl.seek() as number;
          this.progress = typeof p === "number" ? p : 0;
          // 听满 30 秒立即记账：不能只在切歌时才上报，否则一直听下去永远不落库
          if (!reported && playStart && Date.now() - playStart >= 30000 && this.current) {
            reported = true;
            void api.reportTaste(this.current.id, "play", Math.round(this.progress), this.duration);
          }
        }
      }, 1000);
      (this as unknown as { _t?: number })._t = t;
    },
  },
});
