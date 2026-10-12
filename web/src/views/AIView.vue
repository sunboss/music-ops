<script setup lang="ts">
import { computed, ref } from "vue";
import { Sparkles, Mic, Infinity as Inf, Info } from "lucide-vue-next";
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
const lastIntent = ref("");

/** 统一指令：一句话判断意图（点歌 / 电台 / 续播 / 控制），前端负责执行 */
async function ask(text?: string) {
  const input = (text ?? q.value).trim();
  if (!input || busy.value) return;
  q.value = input;
  busy.value = true; err.value = ""; reply.value = ""; songs.value = [];
  try {
    const d = await api.aiAsk(input, p.current?.id, p.queue.map((s) => s.id).slice(-12));
    if (d.error) throw new Error(d.error);
    lastIntent.value = d.intent;
    reply.value = d.reply || "";

    if (d.intent === "control") {
      // 控制类在前端执行最可靠（后端不掌握真实播放状态）
      const c = d.control || "next";
      if (c === "next") p.next();
      else if (c === "prev") p.prev();
      else if (c === "pause") { if (p.playing) p.toggle(); }
      else if (c === "resume") { if (!p.playing) p.toggle(); }
      else if (c === "mute") p.setVolume(p.volume > 0 ? 0 : 1);
      else if (c === "volume_up") p.setVolume(Math.min(1, p.volume + 0.1));
      else if (c === "volume_down") p.setVolume(Math.max(0, p.volume - 0.1));
      return;
    }

    const list = d.songs || [];
    songs.value = list;
    title.value = d.title || "";
    if (list.length && (d.intent === "radio" || d.intent === "continue")) p.playQueue(list, 0);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "请求失败";
  } finally {
    busy.value = false;
  }
}

/** 语音：说完直接走统一指令 */
function voice() {
  const w = window as unknown as { SpeechRecognition?: new () => any; webkitSpeechRecognition?: new () => any };
  const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (!SR) { err.value = "当前浏览器不支持语音识别"; return; }
  const rec = new SR();
  rec.lang = "zh-CN";
  listening.value = true;
  rec.onresult = (e: any) => {
    const t = e.results?.[0]?.[0]?.transcript || "";
    listening.value = false;
    if (t) void ask(t);
  };
  rec.onerror = () => { listening.value = false; err.value = "语音识别失败，请重试"; };
  rec.onend = () => { listening.value = false; };
  rec.start();
}

const intentLabel = computed(() => ({
  play: "点歌", radio: "生成歌单", continue: "接着听", control: "播放控制",
}[lastIntent.value] || ""));
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>AI 音乐</h1>
      <p>一句话就够了：点歌、生成歌单、接着听、控制播放——只给你能完整播放的。</p>
    </header>

    <div class="box">
      <div class="input">
        <Sparkles :size="17" class="ic" />
        <input v-model="q" placeholder="例如：放周杰伦的慢歌 / 再来点类似的 / 下一首"
               @keydown.enter="ask()" />
        <button class="mic" :class="{ on: listening }" title="语音" @click="voice"><Mic :size="17" /></button>
      </div>
      <div class="ops">
        <button class="go" :disabled="busy" @click="ask()">{{ busy ? "处理中…" : "发送" }}</button>
        <span v-if="busy" class="hint">多平台搜索 + 试听校验，约 10–30 秒</span>
      </div>
      <div class="chips">
        <button v-for="s in scenes" :key="s" @click="ask(s)">{{ s }}</button>
      </div>
    </div>

    <!-- 无限电台开关：队列见底时自动续，播放不断档 -->
    <div class="inf" :class="{ on: p.autoContinue }" @click="p.setAutoContinue(!p.autoContinue)">
      <Inf :size="17" />
      <div>
        <b>无限电台</b>
        <span>{{ p.autoContinue ? "开启中：队列快播完时 AI 自动续同类歌" : "已关闭：播完队列就停" }}</span>
      </div>
      <i class="sw" />
    </div>

    <p v-if="err" class="err">{{ err }}</p>
    <div v-if="reply || title" class="head">
      <div v-if="intentLabel" class="tag">{{ intentLabel }}</div>
      <h2 v-if="title">{{ title }}</h2>
      <p v-if="reply">{{ reply }}</p>
    </div>
    <div v-if="songs.length" class="list">
      <SongRow v-for="(s, i) in songs" :key="s.id" :song="s" :index="i"
               :active="p.current?.id === s.id" @play="(idx) => p.playQueue(songs, idx)" />
    </div>
    <p v-if="p.continuing" class="hint" style="padding:0 22px 10px"><Info :size="13" /> AI 正在续歌…</p>
  </div>
</template>

<style scoped>
.page { padding-bottom: 30px; }
.hero { padding: 22px 22px 4px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.box { padding: 16px 22px 0; }
.input { display: flex; align-items: center; gap: 9px; padding: 11px 14px; border-radius: 12px; background: var(--fill); }
.ic { color: var(--acc); flex: none; }
.input input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font-size: 14.5px; color: var(--fg); }
.mic { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: var(--bg-elev);
       color: var(--fg2); flex: none; }
.mic.on { background: #ff453a; color: #fff; animation: pulse 1s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .5 } }
.ops { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.go { padding: 9px 22px; border-radius: 20px; background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.go:disabled { opacity: .6; }
.hint { font-size: 12px; color: var(--fg2); display: inline-flex; align-items: center; gap: 5px; }
.chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.chips button { padding: 5px 12px; border-radius: 14px; background: var(--fill); font-size: 12.5px; color: var(--fg2); }
.inf { display: flex; align-items: center; gap: 12px; margin: 18px 22px 0; padding: 12px 16px;
       border-radius: 12px; background: var(--fill); cursor: pointer; }
.inf.on { background: var(--acc-weak); color: var(--acc); }
.inf div { flex: 1; min-width: 0; }
.inf b { display: block; font-size: 14px; font-weight: 600; }
.inf span { font-size: 12.5px; color: var(--fg2); }
.sw { width: 40px; height: 24px; border-radius: 12px; background: rgba(120,120,128,.3); position: relative; flex: none; }
.sw:after { content: ""; position: absolute; top: 2px; left: 2px; width: 20px; height: 20px; border-radius: 50%;
            background: #fff; transition: transform .2s; }
.inf.on .sw { background: var(--acc); }
.inf.on .sw:after { transform: translateX(16px); }
.err { margin: 14px 22px 0; color: #ff453a; font-size: 13px; }
.head { padding: 18px 22px 4px; }
.tag { display: inline-block; font-size: 11.5px; color: var(--acc); background: var(--acc-weak);
       padding: 2px 9px; border-radius: 11px; margin-bottom: 7px; }
.head h2 { font-size: 20px; font-weight: 700; letter-spacing: -.018em; }
.head p { margin: 4px 0 0; font-size: 13px; color: var(--fg2); }
.list { padding: 8px 10px 0; }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 2px; } .hero h1 { font-size: 24px; }
  .box, .head { padding-left: 14px; padding-right: 14px; }
  .inf { margin: 14px 14px 0; } .err { margin: 12px 14px 0; }
}
</style>
