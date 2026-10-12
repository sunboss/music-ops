<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Play, Heart, MoreHorizontal } from "lucide-vue-next";
import { api } from "@/api/client";
import type { AlbumDetail, Song } from "@/api/types";
import Cover from "@/components/Cover.vue";
import SongRow from "@/components/SongRow.vue";
import { usePlayerStore } from "@/stores/player";

const route = useRoute();
const router = useRouter();
const p = usePlayerStore();
const album = ref<AlbumDetail | null>(null);
const songs = ref<Song[]>([]);
const loading = ref(true);
const err = ref("");

async function load(id: string) {
  loading.value = true; err.value = "";
  try {
    const r = await api.album(id);
    album.value = r.album; songs.value = r.songs;
  } catch (e) { err.value = e instanceof Error ? e.message : "加载失败"; }
  finally { loading.value = false; }
}
onMounted(() => load(String(route.params.id)));
watch(() => route.params.id, (v) => v && load(String(v)));

const artistName = computed(() => album.value?.artist?.name || "");
const artistId = computed(() => album.value?.artist?.id);
const pub = computed(() => {
  const t = album.value?.publishTime;
  if (!t) return "";
  const d = new Date(t);
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日发行`;
});
</script>

<template>
  <div class="page">
    <p v-if="err" class="err">加载失败：{{ err }}</p>
    <template v-if="album">
      <header class="hero">
        <Cover :src="album.picUrl" :alt="album.name" radius="10px" class="pc" eager />
        <div class="info">
          <div class="kind">专辑</div>
          <h1 class="clamp2">{{ album.name }}</h1>
          <div class="meta">
            <a v-if="artistId" @click="router.push(`/artist/${artistId}`)">{{ artistName }}</a>
            <span v-if="pub"> · {{ pub }}</span>
            <span> · {{ songs.length }} 首</span>
          </div>
          <div class="ops">
            <button class="play" @click="p.playQueue(songs, 0)"><Play :size="15" fill="currentColor" />播放</button>
            <button class="chip"><Heart :size="15" /></button>
            <button class="chip"><MoreHorizontal :size="15" /></button>
          </div>
        </div>
      </header>
      <div class="list">
        <SongRow v-for="(s, i) in songs" :key="s.id" :song="s" :index="i" class="vrow"
                 :active="p.current?.id === s.id" @play="(idx) => p.playQueue(songs, idx)" />
      </div>
    </template>
    <div v-else-if="loading" class="skeleton"><div class="sk-cover" /></div>
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
.meta a { color: var(--acc); cursor: pointer; }
.ops { display: flex; gap: 8px; margin-top: 14px; }
.play { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 20px;
        background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.chip { width: 34px; height: 34px; border-radius: 50%; background: var(--fill); display: grid; place-items: center; }
.list { padding: 6px 10px 0; }
.vrow { content-visibility: auto; contain-intrinsic-size: 56px; }
.skeleton { padding: 24px 22px; }
.sk-cover { width: 172px; height: 172px; border-radius: 10px; background: var(--fill); }
@media (max-width: 640px) {
  .hero { gap: 14px; padding: 14px 14px 6px; }
  .pc { width: 118px; } h1 { font-size: 19px; }
  .list { padding: 2px 4px 0; }
}
</style>
