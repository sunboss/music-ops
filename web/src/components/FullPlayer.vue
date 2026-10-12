<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  ChevronDown, Pause, Play, SkipBack, SkipForward, Repeat, Shuffle, ListMusic, Volume2,
} from "lucide-vue-next";
import { usePlayerStore } from "@/stores/player";
import { activeLine } from "@/utils/lrc";
import Cover from "./Cover.vue";

const p = usePlayerStore();
const showLyric = ref(true);
const lyricBox = ref<HTMLElement | null>(null);

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const pct = computed(() => (p.duration ? Math.min(100, (p.progress / p.duration) * 100) : 0));
const artist = computed(() => (p.current?.ar || []).map((a) => a.name).join(", "));
const cur = computed(() => activeLine(p.lyrics, p.progress));

watch(() => p.current?.id, () => { void p.loadLyrics(); });
watch(cur, async (i) => {
  if (i < 0 || !lyricBox.value) return;
  await nextTick();
  const el = lyricBox.value.querySelector<HTMLElement>(`[data-i="${i}"]`);
  if (el) lyricBox.value.scrollTo({ top: el.offsetTop - lyricBox.value.clientHeight / 2 + el.clientHeight / 2, behavior: "smooth" });
});
function seek(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement;
  const r = el.getBoundingClientRect();
  p.seekRatio((e.clientX - r.left) / r.width);
}
function onKey(e: KeyboardEvent) {
  if (!p.showFull) return;
  if (e.key === "Escape") p.showFull = false;
  if (e.key === " ") { e.preventDefault(); p.toggle(); }
}
onMounted(() => { window.addEventListener("keydown", onKey); void p.loadLyrics(); });
onUnmounted(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <Transition name="up">
    <div v-if="p.showFull && p.current" class="fp" :class="{ dark: true }">
      <div class="bg" :style="p.current.al?.picUrl ? { backgroundImage: `url(${p.current.al.picUrl})` } : {}" />
      <header class="hd">
        <button class="ib" @click="p.showFull = false"><ChevronDown :size="22" /></button>
        <div class="ttl">
          <div class="from">正在播放</div>
          <div class="nm ellipsis">{{ p.current.name }}</div>
        </div>
        <button class="ib" :class="{ on: !showLyric }" title="歌词" @click="showLyric = !showLyric">词</button>
      </header>

      <div class="body">
        <div class="art">
          <Cover :src="p.current.al?.picUrl" :alt="p.current.name" radius="12px" class="big" eager />
          <div class="meta">
            <div class="nm2 ellipsis">{{ p.current.name }}</div>
            <div class="ar2 ellipsis">{{ artist }}</div>
          </div>
        </div>

        <div v-show="showLyric" ref="lyricBox" class="lyr no-scrollbar">
          <div v-if="!p.lyrics.length" class="lyr-empty">暂无歌词</div>
          <div v-for="(l, i) in p.lyrics" :key="i" :data-i="i" class="ln"
               :class="{ on: i === cur, past: i < cur }" @click="p.seekRatio(l.t / (p.duration || 1))">
            <div>{{ l.text }}</div>
            <div v-if="l.tr" class="tr">{{ l.tr }}</div>
          </div>
        </div>
      </div>

      <footer class="ft">
        <div class="track" @click="seek"><i :style="{ width: pct + '%' }" /></div>
        <div class="times tnum"><span>{{ fmt(p.progress) }}</span><span>{{ fmt(p.duration) }}</span></div>
        <div class="ctl">
          <button class="ib sm"><Shuffle :size="17" /></button>
          <button class="ib" @click="p.prev()"><SkipBack :size="24" fill="currentColor" /></button>
          <button class="ib play" @click="p.toggle()">
            <Pause v-if="p.playing" :size="28" fill="currentColor" />
            <Play v-else :size="28" fill="currentColor" />
          </button>
          <button class="ib" @click="p.next()"><SkipForward :size="24" fill="currentColor" /></button>
          <button class="ib sm"><Repeat :size="17" /></button>
        </div>
        <div class="ctl2">
          <Volume2 :size="15" />
          <input class="vol" type="range" min="0" max="1" step="0.01" :value="p.volume"
                 @input="p.setVolume(Number(($event.target as HTMLInputElement).value))" />
          <button class="ib sm" title="播放队列"><ListMusic :size="17" /></button>
        </div>
      </footer>
    </div>
  </Transition>
</template>

<style scoped>
.fp { position: fixed; inset: 0; z-index: 60; display: flex; flex-direction: column; color: #fff; overflow: hidden; }
.bg { position: absolute; inset: -20%; background-size: cover; background-position: center;
      filter: blur(60px) saturate(150%) brightness(.5); transform: scale(1.2); }
.fp:before { content: ""; position: absolute; inset: 0; background: rgba(0,0,0,.55); }
.hd, .body, .ft { position: relative; z-index: 1; }
.hd { display: flex; align-items: center; gap: 12px; padding: 14px 18px 6px; }
.hd .ttl { flex: 1; min-width: 0; text-align: center; }
.hd .from { font-size: 11px; opacity: .65; letter-spacing: .04em; }
.hd .nm { font-size: 13.5px; font-weight: 600; }
.ib { width: 40px; height: 40px; display: grid; place-items: center; border-radius: 50%; color: #fff; opacity: .92; }
.ib:hover { background: rgba(255,255,255,.14); }
.ib.sm { width: 34px; height: 34px; opacity: .7; }
.ib.on { background: rgba(255,255,255,.2); }
.body { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6vw; padding: 10px 4vw; min-height: 0; }
.art { width: min(38vh, 420px); flex: none; text-align: center; }
.big { box-shadow: 0 30px 80px rgba(0,0,0,.55); }
.meta { margin-top: 20px; }
.nm2 { font-size: 20px; font-weight: 700; letter-spacing: -.02em; }
.ar2 { font-size: 14px; opacity: .7; margin-top: 2px; }
.lyr { width: min(46vw, 520px); height: min(56vh, 560px); overflow-y: auto; scroll-behavior: smooth;
       mask-image: linear-gradient(transparent, #000 18%, #000 82%, transparent); padding: 40% 0; }
.ln { font-size: 17px; line-height: 1.5; padding: 7px 0; opacity: .42; transition: opacity .25s, transform .25s;
      cursor: pointer; }
.ln.on { opacity: 1; font-weight: 600; transform: scale(1.03); }
.ln.past { opacity: .3; }
.tr { font-size: 13.5px; opacity: .75; font-weight: 400; margin-top: 2px; }
.lyr-empty { opacity: .5; font-size: 14px; text-align: center; padding-top: 40%; }
.ft { padding: 6px 6vw 26px; }
.track { height: 4px; border-radius: 3px; background: rgba(255,255,255,.24); cursor: pointer; }
.track i { display: block; height: 100%; border-radius: 3px; background: #fff; }
.times { display: flex; justify-content: space-between; font-size: 11.5px; opacity: .7; margin-top: 6px; }
.ctl { display: flex; align-items: center; justify-content: center; gap: 22px; margin-top: 6px; }
.ib.play { width: 60px; height: 60px; background: rgba(255,255,255,.16); }
.ctl2 { display: flex; align-items: center; justify-content: flex-end; gap: 10px; margin-top: 10px; }
.vol { width: 120px; accent-color: #fff; }
.up-enter-active, .up-leave-active { transition: transform .3s ease, opacity .3s ease; }
.up-enter-from, .up-leave-to { transform: translateY(3%); opacity: 0; }

@media (max-width: 900px) {
  .body { flex-direction: column; gap: 18px; padding: 4px 22px; justify-content: flex-start; }
  .art { width: min(62vw, 300px); }
  .big { box-shadow: 0 18px 50px rgba(0,0,0,.5); }
  .nm2 { font-size: 18px; }
  .lyr { width: 100%; height: 38vh; padding: 18vh 0; }
  .ln { font-size: 15.5px; }
  .ft { padding: 6px 22px calc(20px + env(safe-area-inset-bottom)); }
  .ctl { gap: 16px; }
  .ctl2 { display: none; }
}
</style>
