<script setup lang="ts">
import { ref } from "vue";
import { Sparkles, Mic } from "lucide-vue-next";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import SongRow from "@/components/SongRow.vue";
import { usePlayerStore } from "@/stores/player";

const p = usePlayerStore();
const scenes = ["深夜写代码", "开车兜风", "运动健身", "专注学习", "助眠放松", "心情不好"];
const q = ref("");
const busy = ref(false);
const reply = ref("");
const title = ref("");
const songs = ref<Song[]>([]);
const err = ref("");
const listening = ref(false);

async function ask(mode: "song" | "radio", text?: string) {
  const input = (text ?? q.value).trim();
  if (!input || busy.value) return;
  q.value = input;
  busy.value = true; err.value = ""; reply.value = ""; songs.value = [];
  try {
    if (mode === "radio") {
      const d = await api.aiRadio(input, 15);
      if (d.error) throw new Error(d.error);
      title.value = d.title || ""; reply.value = (d.reply || "") + (d.picked ? `　AI 精选 ${d.picked} 首` : "");
      songs.value = d.songs || [];
      if (songs.value.length) p.playQueue(songs.value, 0);
    } else {
      const d = await api.aiQuery(input, 8);
      if (d.error) throw new Error(d.error);
      reply.value = d.reply || "";
      songs.value = d.songs || [];
    }
  } catch (e) {
    err.value = e instanceof Error ? e.message : "请求失败";
  } finally {
    busy.value = false;
  }
}

/** 语音点歌：浏览器原生语音识别（HTTPS 下可用） */
function voice() {
  const SR = (window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any })
    .SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: new () => any }).webkitSpeechRecognition;
  if (!SR) { err.value = "当前浏览器不支持语音识别"; return; }
  const rec = new SR();
  rec.lang = "zh-CN";
  listening.value = true;
  rec.onresult = (e: any) => {
    const t = e.results?.[0]?.[0]?.transcript || "";
    listening.value = false;
    if (t) void ask("radio", t);
  };
  rec.onerror = () => { listening.value = false; err.value = "语音识别失败，请重试"; };
  rec.onend = () => { listening.value = false; };
  rec.start();
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>AI 音乐</h1>
      <p>说一句想要什么，我来挑歌——只给你能完整播放的。</p>
    </header>

    <div class="box">
      <div class="input">
        <Sparkles :size="17" class="ic" />
        <input v-model="q" placeholder="例如：深夜写代码听的、周杰伦的慢歌、开车时的粤语老歌"
               @keydown.enter="ask('radio')" />
        <button class="mic" :class="{ on: listening }" title="语音点歌" @click="voice"><Mic :size="17" /></button>
      </div>
      <div class="ops">
        <button class="go" :disabled="busy" @click="ask('radio')">
          {{ busy ? "编排中…" : "生成电台" }}
        </button>
        <button class="go ghost" :disabled="busy" @click="ask('song')">只点几首</button>
        <span v-if="busy" class="hint">正在多平台搜索并试听校验，约 10–30 秒</span>
      </div>
      <div class="chips">
        <button v-for="s in scenes" :key="s" @click="ask('radio', s)">{{ s }}</button>
      </div>
    </div>

    <p v-if="err" class="err">{{ err }}</p>
    <div v-if="title || reply" class="head">
      <h2 v-if="title">{{ title }}</h2>
      <p v-if="reply">{{ reply }}</p>
    </div>
    <div v-if="songs.length" class="list">
      <SongRow v-for="(s, i) in songs" :key="s.id" :song="s" :index="i"
               :active="p.current?.id === s.id" @play="(idx) => p.playQueue(songs, idx)" />
    </div>
  </div>
</template>

<style scoped>
.page { padding-bottom: 30px; }
.hero { padding: 22px 22px 4px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.box { padding: 16px 22px 0; }
.input { display: flex; align-items: center; gap: 9px; padding: 11px 14px; border-radius: 12px;
         background: var(--fill); }
.ic { color: var(--acc); flex: none; }
.input input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font-size: 14.5px; color: var(--fg); }
.mic { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: var(--bg-elev);
       color: var(--fg2); flex: none; }
.mic.on { background: #ff453a; color: #fff; animation: pulse 1s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .5 } }
.ops { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.go { padding: 9px 20px; border-radius: 20px; background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.go.ghost { background: var(--fill); color: var(--fg); }
.go:disabled { opacity: .6; }
.hint { font-size: 12px; color: var(--fg2); }
.chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.chips button { padding: 5px 12px; border-radius: 14px; background: var(--fill); font-size: 12.5px; color: var(--fg2); }
.chips button:hover { color: var(--fg); }
.err { margin: 14px 22px 0; color: #ff453a; font-size: 13px; }
.head { padding: 18px 22px 4px; }
.head h2 { font-size: 20px; font-weight: 700; letter-spacing: -.018em; }
.head p { margin: 4px 0 0; font-size: 13px; color: var(--fg2); }
.list { padding: 8px 10px 0; }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 2px; } .hero h1 { font-size: 24px; }
  .box { padding: 12px 14px 0; } .head { padding: 14px 14px 2px; } .err { margin: 12px 14px 0; }
}
</style>
