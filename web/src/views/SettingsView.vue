<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Sun, Moon, MonitorSmartphone, Trash2, Check, Cast } from "lucide-vue-next";
import { haCfg, haSave, haPlayers, haHint } from "@/utils/ha";
import { usePlayerStore } from "@/stores/player";
import { readHistory, clearHistory } from "@/utils/history";

const p = usePlayerStore();
const theme = ref(localStorage.getItem("theme") || "system");
const info = ref<{ build?: string; ai?: boolean; ai_model?: string; sources?: string }>({});
const saved = ref(false);
const histCount = ref(readHistory().length);

// 投屏：地址与长期令牌只存本机浏览器
const haUrl = ref(haCfg().url);
const haToken = ref(haCfg().token);
const haMsg = ref("");
const haOk = ref(false);
const haTesting = ref(false);

function saveHa() {
  haSave(haUrl.value, haToken.value);
  haOk.value = true;
  haMsg.value = "已保存到本机浏览器";
}

async function testHa() {
  saveHa();
  haTesting.value = true;
  haMsg.value = "";
  try {
    const list = await haPlayers();
    haOk.value = true;
    haMsg.value = list.length
      ? `连上了：找到 ${list.length} 个播放器（${list.slice(0, 3).map((x) => x.name).join("、")}${list.length > 3 ? " 等" : ""}）`
      : "连上了，但还没有播放器：HA 里要加 Music Assistant 或 DLNA / Chromecast 集成";
  } catch (e) {
    haOk.value = false;
    haMsg.value = haHint(e);
  } finally { haTesting.value = false; }
}

const THEMES = [
  { key: "light", label: "浅色", icon: Sun },
  { key: "dark", label: "深色", icon: Moon },
  { key: "system", label: "跟随系统", icon: MonitorSmartphone },
];

function applyTheme() {
  localStorage.setItem("theme", theme.value);
  const dark = theme.value === "dark" ||
    (theme.value === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  saved.value = true;
  window.setTimeout(() => { saved.value = false; }, 1200);
}

function clearLocal() {
  clearHistory();
  histCount.value = 0;
}

onMounted(async () => {
  try {
    const r = await fetch("/api/version");
    info.value = await r.json();
  } catch { /* 后端不可达时静默 */ }
});
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>设置</h1>
      <p>外观、播放与本地数据</p>
    </header>

    <section class="grp">
      <h2>外观</h2>
      <div class="themes">
        <button v-for="t in THEMES" :key="t.key" :class="{ on: theme === t.key }"
                @click="theme = t.key; applyTheme()">
          <component :is="t.icon" :size="17" /><span>{{ t.label }}</span>
          <Check v-if="theme === t.key" :size="14" class="ck" />
        </button>
      </div>
      <p v-if="saved" class="ok">已保存</p>
    </section>

    <section class="grp">
      <h2>播放</h2>
      <div class="row">
        <span>音量</span>
        <input type="range" min="0" max="1" step="0.01" :value="p.volume"
               @input="p.setVolume(Number(($event.target as HTMLInputElement).value))" />
        <b class="tnum">{{ Math.round(p.volume * 100) }}%</b>
      </div>
    </section>

    <section class="grp">
      <h2>本地数据</h2>
      <div class="row">
        <span>播放记录</span><b class="tnum">{{ histCount }} 首</b>
        <button class="ghost" :disabled="!histCount" @click="clearLocal"><Trash2 :size="14" />清空</button>
      </div>
      <p class="note">播放记录只保存在你自己的浏览器里，用于「音乐库 → 最近播放」。</p>
    </section>

    <section class="grp">
      <h2>投屏（Home Assistant）</h2>
      <div class="ha">
        <input v-model="haUrl" placeholder="http://192.168.1.240:8123" inputmode="url" />
        <input v-model="haToken" type="password" placeholder="长期访问令牌（Long-Lived Token）" />
        <div class="haops">
          <button class="ghost" @click="saveHa"><Check :size="14" />保存</button>
          <button class="ghost" :disabled="haTesting" @click="testHa">
            <Cast :size="14" />{{ haTesting ? "测试中…" : "测试连接" }}
          </button>
        </div>
        <p v-if="haMsg" :class="haOk ? 'ok' : 'bad'">{{ haMsg }}</p>
        <p class="note">
          设备都在你家里、服务器在东京够不到，所以投屏要经你家 HA：HA 里的 <b>Music Assistant</b>
          （或 DLNA / Chromecast 集成）把设备暴露出来，播放条上的投屏按钮就能把歌推过去。<br />
          地址与令牌只存在你浏览器本地，不会发到服务器。HA 里生成令牌：个人资料 → 长期访问令牌。
        </p>
      </div>
    </section>

    <section class="grp">
      <h2>关于</h2>
      <div class="kv"><span>构建</span><b>{{ info.build || "—" }}</b></div>
      <div class="kv"><span>换源</span><b>{{ info.sources || "—" }}</b></div>
      <div class="kv"><span>AI</span>
        <b>{{ info.ai ? `已启用 · ${info.ai_model}` : "未配置" }}</b></div>
      <p class="note">
        R-Music · 网易云播放器 + 多平台换源 + AI 点歌。<br />
        前端 Vue 3 / Vite / Tailwind；后端换源适配器跑在国内机，AI 直连 DeepSeek。
      </p>
    </section>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 6px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.grp { padding: 16px 22px 4px; }
.grp h2 { font-size: 12px; font-weight: 600; color: var(--fg3); letter-spacing: .04em; margin-bottom: 10px; }
.themes { display: flex; gap: 10px; flex-wrap: wrap; }
.themes button { display: inline-flex; align-items: center; gap: 8px; padding: 10px 16px; border-radius: 12px;
                 background: var(--fill); font-size: 13.5px; color: var(--fg); }
.themes button.on { background: var(--acc-weak); color: var(--acc); font-weight: 600; }
.ck { margin-left: 2px; }
.row { display: flex; align-items: center; gap: 12px; padding: 10px 0; }
.row > span { flex: none; font-size: 14px; }
.row input[type="range"] { flex: 1; max-width: 240px; accent-color: var(--acc); }
.row b { font-size: 13px; color: var(--fg2); }
.ghost { display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: 14px;
         background: var(--fill); font-size: 12.5px; }
.ghost:disabled { opacity: .5; }
.ok { color: var(--acc); font-size: 12.5px; margin: 8px 0 0; white-space: pre-wrap; }
.bad { color: #ff9f0a; font-size: 12.5px; margin: 8px 0 0; white-space: pre-wrap; line-height: 1.55; }
.ha { display: flex; flex-direction: column; gap: 9px; max-width: 460px; }
.ha input { padding: 10px 13px; border-radius: 10px; background: var(--fill); border: 0; outline: 0;
            font-size: 13.5px; color: var(--fg); }
.haops { display: flex; gap: 9px; flex-wrap: wrap; }
.kv { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 0.5px solid var(--hair); font-size: 13.5px; }
.kv b { color: var(--fg2); font-weight: 500; }
.note { font-size: 12.5px; color: var(--fg2); line-height: 1.6; margin: 10px 0 0; }
@media (max-width: 640px) { .hero { padding: 16px 14px 4px; } .hero h1 { font-size: 24px; } .grp { padding: 14px 14px 2px; } }
</style>
