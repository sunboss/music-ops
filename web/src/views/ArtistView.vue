<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Play } from "lucide-vue-next";
import { api } from "@/api/client";
import type { ArtistDetail, Song } from "@/api/types";
import SongRow from "@/components/SongRow.vue";
import CardGrid from "@/components/CardGrid.vue";
import Section from "@/components/Section.vue";
import { usePlayerStore } from "@/stores/player";

const route = useRoute();
const router = useRouter();
const p = usePlayerStore();
const artist = ref<ArtistDetail | null>(null);
const hot = ref<Song[]>([]);
const albums = ref<{ id: number; name: string; picUrl?: string }[]>([]);
const loading = ref(true);
const showAll = ref(false);

async function load(id: string) {
  loading.value = true;
  try {
    const [a, al] = await Promise.all([api.artist(id), api.artistAlbums(id, 24)]);
    artist.value = a.artist; hot.value = a.hotSongs;
    albums.value = (al as { id: number; name: string; picUrl?: string }[]).map((x) => ({
      id: x.id, name: x.name, picUrl: x.picUrl,
    }));
  } finally { loading.value = false; }
}
onMounted(() => load(String(route.params.id)));
watch(() => route.params.id, (v) => v && load(String(v)));
</script>

<template>
  <div class="page">
    <header class="hero">
      <div class="ava"><img v-if="artist?.picUrl" :src="artist.picUrl" :alt="artist?.name" loading="lazy" /></div>
      <div class="info">
        <div class="kind">歌手</div>
        <h1 class="ellipsis">{{ artist?.name || "…" }}</h1>
        <div class="meta">{{ artist?.musicSize || hot.length }} 首歌 · {{ artist?.albumSize || albums.length }} 张专辑</div>
        <div class="ops">
          <button class="play" @click="p.playQueue(hot, 0)"><Play :size="15" fill="currentColor" />播放热门</button>
        </div>
      </div>
    </header>

    <Section v-if="hot.length" title="热门歌曲" :more="showAll ? '收起' : '查看全部'" @more="showAll = !showAll">
      <div class="list">
        <SongRow v-for="(s, i) in (showAll ? hot : hot.slice(0, 10))" :key="s.id" :song="s" :index="i"
                 class="vrow" :active="p.current?.id === s.id" @play="(idx) => p.playQueue(hot, idx)" />
      </div>
    </Section>

    <Section v-if="albums.length" title="专辑">
      <CardGrid :items="albums" :min="150" @open="(id) => router.push(`/album/${id}`)" />
    </Section>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { display: flex; gap: 20px; padding: 24px 22px 6px; align-items: center; }
.ava { width: 140px; height: 140px; border-radius: 50%; overflow: hidden; flex: none; background: var(--fill);
       box-shadow: 0 10px 28px rgba(0,0,0,.16); }
.ava img { width: 100%; height: 100%; object-fit: cover; display: block; }
.info { min-width: 0; }
.kind { font-size: 11.5px; font-weight: 600; color: var(--fg2); letter-spacing: .04em; }
h1 { font-size: 30px; font-weight: 700; letter-spacing: -.024em; margin: 4px 0 6px; }
.meta { font-size: 12.5px; color: var(--fg2); }
.ops { margin-top: 14px; }
.play { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 20px;
        background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.list { padding: 0 2px; }
.vrow { content-visibility: auto; contain-intrinsic-size: 56px; }
@media (max-width: 640px) {
  .hero { gap: 14px; padding: 14px 14px 4px; }
  .ava { width: 88px; height: 88px; }
  h1 { font-size: 21px; }
}
</style>
