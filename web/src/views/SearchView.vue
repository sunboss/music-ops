<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Search as SearchIcon } from "lucide-vue-next";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import SongRow from "@/components/SongRow.vue";
import CardGrid from "@/components/CardGrid.vue";
import Cover from "@/components/Cover.vue";
import { usePlayerStore } from "@/stores/player";

const route = useRoute();
const router = useRouter();
const p = usePlayerStore();

const TABS = [
  { key: 1, label: "单曲" }, { key: 10, label: "专辑" },
  { key: 100, label: "歌手" }, { key: 1000, label: "歌单" },
];
const kw = ref("");
const tab = ref(1);
const busy = ref(false);
const songs = ref<Song[]>([]);
const albums = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const artists = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const playlists = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const history = ref<string[]>(JSON.parse(localStorage.getItem("searchHistory") || "[]"));

const hot = ["周杰伦", "陈奕迅", "Beyond", "深夜写代码", "粤语老歌", "纯音乐"];

async function run(k?: string, t?: number) {
  const q = (k ?? kw.value).trim();
  if (!q) return;
  kw.value = q;
  if (t) tab.value = t;
  busy.value = true;
  history.value = [q, ...history.value.filter((x) => x !== q)].slice(0, 8);
  localStorage.setItem("searchHistory", JSON.stringify(history.value));
  try {
    const r = await api.search(q, tab.value, 40);
    songs.value = r.songs;
    albums.value = (r.albums as { id: number; name: string; picUrl?: string; artist?: { name: string } }[])
      .map((x) => ({ id: x.id, name: x.name, picUrl: x.picUrl, sub: x.artist?.name }));
    artists.value = (r.artists as { id: number; name: string; picUrl?: string; albumSize?: number }[])
      .map((x) => ({ id: x.id, name: x.name, picUrl: x.picUrl, sub: x.albumSize ? `${x.albumSize} 张专辑` : "" }));
    playlists.value = (r.playlists as { id: number; name: string; picUrl?: string; trackCount?: number }[])
      .map((x) => ({ id: x.id, name: x.name, picUrl: x.picUrl, sub: x.trackCount ? `${x.trackCount} 首` : "" }));
  } finally { busy.value = false; }
}

onMountedOnce();
function onMountedOnce() {
  const q = String(route.params.keywords || "");
  if (q) { kw.value = q; void run(q); }
}
watch(() => route.params.keywords, (v) => v && void run(String(v)));
watch(tab, () => { if (kw.value) void run(); });

const hasResult = computed(() =>
  (tab.value === 1 && songs.value.length) || (tab.value === 10 && albums.value.length) ||
  (tab.value === 100 && artists.value.length) || (tab.value === 1000 && playlists.value.length));
</script>

<template>
  <div class="page">
    <div class="bar">
      <SearchIcon :size="17" class="ic" />
      <input v-model="kw" placeholder="搜索歌曲 / 歌手 / 歌单" @keydown.enter="run()" />
      <button v-if="kw" class="clr" @click="kw = ''">✕</button>
    </div>

    <div v-if="!hasResult && !busy" class="empty">
      <template v-if="history.length">
        <div class="eh">最近搜索</div>
        <div class="chips"><button v-for="h in history" :key="h" @click="run(h)">{{ h }}</button></div>
      </template>
      <div class="eh">热门搜索</div>
      <div class="chips"><button v-for="h in hot" :key="h" @click="run(h)">{{ h }}</button></div>
    </div>

    <div class="tabs">
      <button v-for="t in TABS" :key="t.key" :class="{ on: tab === t.key }" @click="tab = t.key">{{ t.label }}</button>
    </div>

    <p v-if="busy" class="tip">搜索中…</p>
    <template v-else>
      <div v-if="tab === 1" class="list">
        <SongRow v-for="(s, i) in songs" :key="s.id" :song="s" :index="i" class="vrow"
                 :active="p.current?.id === s.id" @play="(idx) => p.playQueue(songs, idx)" />
        <p v-if="!songs.length" class="tip">没有找到单曲</p>
      </div>
      <div v-else-if="tab === 10" class="wrap">
        <CardGrid :items="albums" @open="(id) => router.push(`/album/${id}`)" />
        <p v-if="!albums.length" class="tip">没有找到专辑</p>
      </div>
      <div v-else-if="tab === 100" class="wrap">
        <div class="agrid">
          <div v-for="a in artists" :key="a.id" class="acard" @click="router.push(`/artist/${a.id}`)">
            <div class="aava">
              <img v-if="a.picUrl" :src="a.picUrl" :alt="a.name" loading="lazy" />
            </div>
            <div class="an ellipsis">{{ a.name }}</div>
            <div class="as ellipsis">{{ a.sub }}</div>
          </div>
        </div>
        <p v-if="!artists.length" class="tip">没有找到歌手</p>
      </div>
      <div v-else class="wrap">
        <CardGrid :items="playlists" @open="(id) => router.push(`/playlist/${id}`)" />
        <p v-if="!playlists.length" class="tip">没有找到歌单</p>
      </div>
    </template>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.bar { display: flex; align-items: center; gap: 9px; margin: 16px 22px 6px; padding: 10px 14px;
       border-radius: 12px; background: var(--fill); }
.ic { color: var(--fg2); flex: none; }
.bar input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font-size: 15px; color: var(--fg); }
.clr { color: var(--fg3); }
.tabs { display: flex; gap: 6px; padding: 10px 22px 4px; }
.tabs button { padding: 5px 14px; border-radius: 14px; font-size: 13px; color: var(--fg2); background: var(--fill); }
.tabs button.on { background: var(--acc); color: #fff; font-weight: 600; }
.list { padding: 8px 10px 0; }
.wrap { padding: 12px 22px 0; }
.vrow { content-visibility: auto; contain-intrinsic-size: 56px; }
.tip { padding: 26px 22px; color: var(--fg2); font-size: 13px; }
.empty { padding: 18px 22px 0; }
.eh { font-size: 12px; color: var(--fg3); letter-spacing: .04em; margin: 10px 0 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chips button { padding: 6px 13px; border-radius: 15px; background: var(--fill); font-size: 13px; color: var(--fg2); }
.agrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 18px; }
.acard { text-align: center; cursor: pointer; }
.aava { width: 96px; height: 96px; margin: 0 auto 9px; border-radius: 50%; overflow: hidden; background: var(--fill); }
.aava img { width: 100%; height: 100%; object-fit: cover; }
.an { font-size: 13.5px; font-weight: 500; }
.as { font-size: 12px; color: var(--fg2); }
@media (max-width: 640px) {
  .bar { margin: 12px 14px 4px; }
  .tabs { padding: 8px 14px 2px; overflow-x: auto; }
  .list { padding: 6px 4px 0; }
  .wrap, .empty { padding-left: 14px; padding-right: 14px; }
}
</style>
