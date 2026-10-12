<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { Play, History, Sparkles, ListMusic, Trash2, Heart, Radio, Download } from "lucide-vue-next";
import { readFavs, favSongs, toggleFav } from "@/utils/favorites";
import { readHistory, clearHistory, type HistoryItem } from "@/utils/history";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import Cover from "@/components/Cover.vue";
import CardGrid from "@/components/CardGrid.vue";
import { usePlayerStore } from "@/stores/player";

const router = useRouter();
const p = usePlayerStore();
const tab = ref<"recent" | "fav" | "daily" | "playlist">("recent");
const favs = ref(readFavs());
const radioBusy = ref(false);
const warmMsg = ref("");
const warmBusy = ref(false);
const history = ref<HistoryItem[]>(readHistory());
const daily = ref<Song[]>([]);
const playlists = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const busy = ref(false);
const loading = ref(false);

/** 历史里只存了 id/名字，播放前补全时长等信息 */
const recentSongs = computed<Song[]>(() => history.value.map((h) => ({
  id: h.id, name: h.name, dt: 0,
  ar: [{ id: 0, name: h.artist }],
  al: { id: h.albumId || 0, name: "", picUrl: h.pic },
} as Song)));

async function playHistory() {
  if (!recentSongs.value.length || busy.value) return;
  busy.value = true;
  try {
    const detail = await api.songDetail(recentSongs.value.slice(0, 100).map((s) => s.id));
    const byId = new Map(detail.map((s) => [String(s.id), s]));
    p.playQueue(recentSongs.value.map((s) => byId.get(String(s.id)) || s), 0);
  } finally { busy.value = false; }
}

async function loadDaily() {
  if (daily.value.length) return;
  loading.value = true;
  try { daily.value = await api.dailySongs(); } finally { loading.value = false; }
}
async function loadPlaylists() {
  if (playlists.value.length) return;
  loading.value = true;
  try {
    const list = await api.userPlaylists();
    playlists.value = list.map((x) => ({
      id: x.id, name: x.name, picUrl: x.coverImgUrl,
      sub: x.trackCount ? `${x.trackCount} 首` : "",
    }));
  } finally { loading.value = false; }
}

function drop() { clearHistory(); history.value = []; }

/** 播收藏（时长等信息播放时由播放器补全） */
function playFavs(ind = 0) {
  const list = favSongs();
  if (list.length) p.playQueue(list, ind);
}

/** 按收藏生成电台：交给 AI，它拿到的口味上下文里"明确收藏"权重最高 */
async function favRadio() {
  if (radioBusy.value) return;
  radioBusy.value = true;
  try {
    const d = await api.aiRadio("像我收藏的那些歌", 15);
    if (d.songs?.length) p.playQueue(d.songs, 0);
  } finally { radioBusy.value = false; }
}

/** 离线保存：整批收藏提前落到服务器本地盘，点下去立刻响 */
async function warmFavs() {
  if (warmBusy.value || !favs.value.length) return;
  warmBusy.value = true;
  warmMsg.value = "保存中…";
  try {
    const r = await api.warmup(favs.value.map((f) => f.id));
    warmMsg.value = r.accepted
      ? `已加入保存队列 ${r.accepted} 首（新 ${r.accepted} / 已存 ${r.cached}）`
      : `全部已保存（${r.cached} 首）`;
  } catch {
    warmMsg.value = "保存失败，稍后再试";
  } finally {
    warmBusy.value = false;
    setTimeout(() => (warmMsg.value = ""), 6000);
  }
}

function removeFav(id: number) {
  const song = favSongs().find((s) => String(s.id) === String(id));
  if (song) toggleFav(song);
  favs.value = readFavs();
}
function pick(t: typeof tab.value) {
  tab.value = t;
  if (t === "daily") void loadDaily();
  if (t === "playlist") void loadPlaylists();
}
onMounted(() => {
  if (!history.value.length) { tab.value = "daily"; void loadDaily(); }
});
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>音乐库</h1>
      <p>播放记录存在你自己的浏览器里，随时可用</p>
    </header>

    <div class="tabs">
      <button :class="{ on: tab === 'recent' }" @click="pick('recent')"><History :size="15" />最近播放</button>
      <button :class="{ on: tab === 'fav' }" @click="pick('fav')"><Heart :size="15" />我喜欢的</button>
      <button :class="{ on: tab === 'daily' }" @click="pick('daily')"><Sparkles :size="15" />每日推荐</button>
      <button :class="{ on: tab === 'playlist' }" @click="pick('playlist')"><ListMusic :size="15" />歌单</button>
    </div>

    <template v-if="tab === 'recent'">
      <div v-if="history.length" class="ops">
        <button class="play" :disabled="busy" @click="playHistory">
          <Play :size="15" fill="currentColor" />{{ busy ? "准备中…" : "播放全部" }}
        </button>
        <button class="ghost" @click="drop"><Trash2 :size="14" />清空</button>
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
      <p v-if="!history.length" class="tip">还没有播放记录。随便播一首，这里就会记下来（只存在你自己的浏览器里）。</p>
    </template>

    <template v-else-if="tab === 'fav'">
      <div v-if="favs.length" class="ops">
        <button class="play" @click="playFavs()"><Play :size="15" fill="currentColor" />播放全部</button>
        <button class="ghost" :disabled="radioBusy" @click="favRadio">
          <Radio :size="14" />{{ radioBusy ? "生成中…" : "按收藏生成电台" }}
        </button>
        <button class="ghost" :disabled="warmBusy" @click="warmFavs" title="提前下载到服务器，点播零等待">
          <Download :size="14" />{{ warmBusy ? "保存中…" : "离线保存" }}
        </button>
        <span class="cnt">{{ favs.length }} 首 · 会喂给 AI 推荐</span>
        <span v-if="warmMsg" class="cnt warm-msg">{{ warmMsg }}</span>
      </div>
      <p v-if="!favs.length" class="tip">
        还没有收藏。在播放器上点红心就会记到这里 —— 收藏会喂给 AI，之后说一句「像我喜欢的」它就更准。
      </p>
      <div v-else class="list">
        <div v-for="(f, i) in favs" :key="f.id" class="row" :class="{ on: p.current?.id === Number(f.id) }"
             @dblclick="playFavs(i)">
          <div class="ix tnum">{{ i + 1 }}</div>
          <Cover :src="f.pic" :alt="f.name" radius="6px" class="thumb" />
          <div class="mm">
            <div class="nm ellipsis">{{ f.name }}</div>
            <div class="ar ellipsis">{{ f.artist }}</div>
          </div>
          <button class="pb" title="取消喜欢" @click.stop="removeFav(f.id)"><Heart :size="14" fill="currentColor" /></button>
        </div>
      </div>
    </template>

    <template v-else-if="tab === 'daily'">
      <div v-if="daily.length" class="ops">
        <button class="play" @click="p.playQueue(daily, 0)"><Play :size="15" fill="currentColor" />播放全部</button>
        <span class="cnt">{{ daily.length }} 首 · 按你的口味更新</span>
      </div>
      <p v-if="loading" class="tip">加载中…</p>
      <p v-else-if="!daily.length" class="tip">暂时没有推荐数据，稍后重试。</p>
      <div v-else class="list">
        <div v-for="(s, i) in daily" :key="s.id" class="row" :class="{ on: p.current?.id === s.id }"
             @dblclick="p.playQueue(daily, i)">
          <div class="ix tnum">{{ i + 1 }}</div>
          <Cover :src="s.al?.picUrl" :alt="s.name" radius="6px" class="thumb" />
          <div class="mm">
            <div class="nm ellipsis">{{ s.name }}</div>
            <div class="ar ellipsis">{{ (s.ar || []).map((a) => a.name).join(", ") }}</div>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <p v-if="loading" class="tip">加载中…</p>
      <p v-else-if="!playlists.length" class="tip">暂时拿不到歌单列表，稍后重试。</p>
      <div v-else class="wrap">
        <CardGrid :items="playlists" @open="(id) => router.push(`/playlist/${id}`)" />
      </div>
    </template>
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
.wrap { padding: 4px 22px 0; }
.row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 8px;
       border-bottom: 0.5px solid var(--hair); }
.row:hover, .row.on { background: var(--fill); }
.ix { width: 20px; text-align: center; font-size: 13px; color: var(--fg3); flex: none; }
.thumb { width: 42px; flex: none; }
.mm { flex: 1; min-width: 0; }
.nm { font-size: 14.5px; font-weight: 500; letter-spacing: -.012em; }
.ar { font-size: 12.5px; color: var(--fg2); }
.pb { width: 32px; height: 32px; display: grid; place-items: center; color: #ff375f; }
.warm-msg { color: var(--accent); }
.tip { padding: 26px 22px; color: var(--fg2); font-size: 13px; max-width: 520px; }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 8px; } .hero h1 { font-size: 24px; }
  .tabs { padding: 0 14px 6px; overflow-x: auto; }
  .ops { padding: 4px 14px 6px; } .list { padding: 2px 4px 0; } .wrap { padding: 4px 14px 0; }
}
</style>
