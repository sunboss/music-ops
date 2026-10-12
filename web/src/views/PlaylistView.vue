<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { Play, Heart, MoreHorizontal, Shuffle } from "lucide-vue-next";
import { api } from "@/api/client";
import type { Playlist, Song } from "@/api/types";
import Cover from "@/components/Cover.vue";
import SongRow from "@/components/SongRow.vue";
import { usePlayerStore } from "@/stores/player";

const route = useRoute();
const p = usePlayerStore();
const pl = ref<Playlist | null>(null);
const songs = ref<Song[]>([]);
const loading = ref(true);
const err = ref("");
const deadCount = computed(() => songs.value.filter((s) => s.playable === false).length);

async function load(id: string) {
  loading.value = true; err.value = "";
  try {
    const detail = await api.playlist(id);
    pl.value = detail;
    songs.value = detail?.tracks?.length ? detail.tracks : await api.playlistTracks(id, 1000);
    if (!songs.value.length) songs.value = await api.playlistTracks(id, 1000);
  } catch (e) {
    err.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => load(String(route.params.id)));
watch(() => route.params.id, (v) => v && load(String(v)));

const updateStr = computed(() => {
  const t = pl.value?.updateTime;
  if (!t) return "";
  const d = new Date(t);
  return `最后更新于 ${d.getFullYear()}年${String(d.getMonth() + 1).padStart(2, "0")}月${String(d.getDate()).padStart(2, "0")}日`;
});
</script>

<template>
  <div class="page">
    <p v-if="err" class="err">加载失败：{{ err }}</p>
    <template v-if="pl">
      <header class="hero">
        <Cover :src="pl.coverImgUrl" :alt="pl.name" radius="10px" class="pc" eager />
        <div class="info">
          <div class="kind">歌单</div>
          <h1 class="clamp2">{{ pl.name }}</h1>
          <div class="meta">
            {{ pl.creator?.nickname }} · {{ pl.trackCount || songs.length }} 首
            <template v-if="updateStr"> · {{ updateStr }}</template>
          </div>
          <p v-if="pl.description" class="desc clamp2">{{ pl.description }}</p>
          <div class="ops">
            <button class="play" @click="p.playQueue(songs, 0)"><Play :size="15" fill="currentColor" />播放</button>
            <button class="chip"><Shuffle :size="15" /></button>
            <button class="chip"><Heart :size="15" /></button>
            <button class="chip"><MoreHorizontal :size="15" /></button>
          </div>
        </div>
      </header>

      <div class="list">
        <div class="lhead">
          <span>#</span><span>标题</span>
          <span v-if="$route.name" class="col-al">专辑</span><span class="col-du">时长</span>
        </div>
        <SongRow
          v-for="(s, i) in songs" :key="s.id" :song="s" :index="i" class="vrow"
          :active="p.current?.id === s.id" :show-album="true"
          @play="(idx) => p.playQueue(songs, idx)"
        />
        <p v-if="deadCount" class="dead-note">其中 {{ deadCount }} 首暂无完整音源（已置灰）</p>
      </div>
    </template>
    <div v-else-if="loading" class="skeleton">
      <div class="sk-cover" /><div class="sk-lines"><div /><div /><div /></div>
    </div>
  </div>
</template>

<style scoped>
.page { padding-bottom: 30px; }
.err { padding: 20px 22px; color: #ff453a; }
.hero { display: flex; gap: 20px; padding: 24px 22px 14px; align-items: flex-end; }
.pc { width: 172px; flex: none; box-shadow: 0 10px 28px rgba(0,0,0,.16); }
.info { min-width: 0; flex: 1; }
.kind { font-size: 11.5px; font-weight: 600; color: var(--fg2); letter-spacing: .04em; }
h1 { font-size: 28px; font-weight: 700; letter-spacing: -.024em; margin: 4px 0 6px; line-height: 1.18; }
.meta { font-size: 12.5px; color: var(--fg2); }
.desc { font-size: 12.5px; color: var(--fg2); margin: 8px 0 0; max-width: 620px; }
.ops { display: flex; gap: 8px; margin-top: 14px; }
.play { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 20px;
        background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.chip { width: 34px; height: 34px; border-radius: 50%; background: var(--fill); display: grid; place-items: center; }
.list { padding: 6px 10px 0; }
.lhead { display: flex; align-items: center; gap: 12px; padding: 4px 12px 8px; font-size: 11.5px;
         color: var(--fg3); border-bottom: 0.5px solid var(--hair); }
.lhead span:first-child { width: 20px; text-align: center; }
.lhead span:nth-child(2) { flex: 1; }
.col-al { width: 26%; }
.col-du { width: 44px; text-align: right; }
/* 1200+ 首列表：用 content-visibility 让浏览器只渲染可视区域，滚动不掉帧 */
.vrow { content-visibility: auto; contain-intrinsic-size: 56px; }
.dead-note { padding: 12px; font-size: 12px; color: var(--fg2); }
.skeleton { display: flex; gap: 20px; padding: 24px 22px; }
.sk-cover { width: 172px; height: 172px; border-radius: 10px; background: var(--fill); flex: none; }
.sk-lines { flex: 1; display: flex; flex-direction: column; gap: 10px; }
.sk-lines div { height: 18px; border-radius: 6px; background: var(--fill); }
.sk-lines div:first-child { width: 55%; height: 26px; }
.sk-lines div:nth-child(2) { width: 35%; }
@media (max-width: 640px) {
  .hero { flex-direction: row; gap: 14px; padding: 14px 14px 6px; align-items: flex-end; }
  .pc { width: 108px; }
  h1 { font-size: 19px; margin-bottom: 4px; }
  .desc, .col-al { display: none; }
  .list { padding: 2px 4px 0; }
}
</style>
