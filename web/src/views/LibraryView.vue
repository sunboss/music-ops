<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { Play, History, Heart, ListMusic, Trash2 } from "lucide-vue-next";
import { readHistory, clearHistory, type HistoryItem } from "@/utils/history";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import Cover from "@/components/Cover.vue";
import SongRow from "@/components/SongRow.vue";
import { usePlayerStore } from "@/stores/player";

const router = useRouter();
const p = usePlayerStore();
const tab = ref<"recent" | "liked" | "playlist">("recent");
const history = ref<HistoryItem[]>(readHistory());
const busy = ref(false);

const recentSongs = computed<Song[]>(() => history.value.map((h) => ({
  id: h.id, name: h.name, dt: 0,
  ar: [{ id: 0, name: h.artist }],
  al: { id: h.albumId || 0, name: "", picUrl: h.pic },
} as Song)));

async function playHistory() {
  if (!recentSongs.value.length || busy.value) return;
  busy.value = true;
  try {
    // 历史里只存了 id/名字，播放前把时长补全（下载进度条才准）
    const detail = await api.songDetail(recentSongs.value.slice(0, 100).map((s) => s.id));
    const byId = new Map(detail.map((s) => [String(s.id), s]));
    const merged = recentSongs.value.map((s) => byId.get(String(s.id)) || s);
    p.playQueue(merged, 0);
  } finally { busy.value = false; }
}

function drop() {
  clearHistory();
  history.value = [];
}
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>音乐库</h1>
      <p>登录后可同步歌单与收藏；未登录也能用本地播放记录</p>
    </header>

    <div class="tabs">
      <button :class="{ on: tab === 'recent' }" @click="tab = 'recent'"><History :size="15" />最近播放</button>
      <button :class="{ on: tab === 'liked' }" @click="tab = 'liked'"><Heart :size="15" />我喜欢的</button>
      <button :class="{ on: tab === 'playlist' }" @click="tab = 'playlist'"><ListMusic :size="15" />我的歌单</button>
    </div>

    <template v-if="tab === 'recent'">
      <div v-if="history.length" class="ops">
        <button class="play" :disabled="busy" @click="playHistory">
          <Play :size="15" fill="currentColor" />{{ busy ? "准备中…" : "播放全部" }}
        </button>
        <button class="ghost" @click="drop"><Trash2 :size="14" />清空记录</button>
        <span class="cnt">{{ history.length }} 首（本地）</span>
      </div>
      <div class="list">
        <div v-for="(h, i) in history" :key="h.id" class="row" :class="{ on: p.current?.id === h.id }"
             @dblclick="p.playQueue(recentSongs, i)">
          <div class="ix tnum">{{ i + 1 }}</div>
          <Cover :src="h.pic" :alt="h.name" radius="6px" class="thumb" />
          <div class="mm">
            <div class="nm ellipsis">{{ h.name }}</div>
            <div class="ar ellipsis">{{ h.artist }}</div>
          </div>
          <button class="pb" @click.stop="p.playQueue(recentSongs, i)"><Play :size="14" fill="currentColor" /></button>
        </div>
      </div>
      <p v-if="!history.length" class="tip">还没有播放记录。随便播一首歌，这里就会记下来（只存在你自己的浏览器里）。</p>
    </template>

    <div v-else class="need-login">
      <div class="nl-icon">{{ tab === "liked" ? "♡" : "☰" }}</div>
      <h2>{{ tab === "liked" ? "登录后查看「我喜欢的音乐」" : "登录后查看你的歌单" }}</h2>
      <p>本站播放与 AI 点歌无需登录；要读取你的网易云歌单与收藏才需要账号。</p>
      <button class="play" @click="router.push('/search/周杰伦')">先去逛逛</button>
    </div>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 10px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.tabs { display: flex; gap: 8px; padding: 0 22px 8px; }
.tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 16px;
               background: var(--fill); font-size: 13px; color: var(--fg2); }
.tabs button.on { background: var(--acc); color: #fff; font-weight: 600; }
.ops { display: flex; align-items: center; gap: 10px; padding: 6px 22px 8px; flex-wrap: wrap; }
.play { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 20px;
        background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.ghost { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 20px;
         background: var(--fill); font-size: 13px; }
.cnt { font-size: 12px; color: var(--fg2); }
.list { padding: 4px 10px 0; }
.row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 8px;
       border-bottom: 0.5px solid var(--hair); }
.row:hover, .row.on { background: var(--fill); }
.ix { width: 20px; text-align: center; font-size: 13px; color: var(--fg3); flex: none; }
.thumb { width: 42px; flex: none; }
.mm { flex: 1; min-width: 0; }
.nm { font-size: 14.5px; font-weight: 500; letter-spacing: -.012em; }
.ar { font-size: 12.5px; color: var(--fg2); }
.pb { width: 32px; height: 32px; display: grid; place-items: center; color: var(--fg2); }
.tip { padding: 30px 22px; color: var(--fg2); font-size: 13px; max-width: 520px; }
.need-login { display: grid; justify-items: center; gap: 6px; padding: 40px 22px; text-align: center; }
.nl-icon { font-size: 38px; color: var(--fg3); }
.need-login h2 { font-size: 18px; font-weight: 700; }
.need-login p { font-size: 13px; color: var(--fg2); max-width: 420px; margin: 0 0 10px; }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 8px; } .hero h1 { font-size: 24px; }
  .tabs { padding: 0 14px 6px; overflow-x: auto; }
  .ops { padding: 4px 14px 6px; } .list { padding: 2px 4px 0; }
}
</style>
