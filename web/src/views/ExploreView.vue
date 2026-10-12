<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import Section from "@/components/Section.vue";
import CardGrid from "@/components/CardGrid.vue";

const router = useRouter();
const CATS = ["全部", "华语", "欧美", "日语", "韩语", "电子", "摇滚", "民谣", "说唱", "轻音乐"];
const cat = ref("全部");
const loading = ref(true);
const toplists = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const playlists = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const albums = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);

async function loadTop() {
  const t = await api.toplists();
  toplists.value = t.filter((x) => !/云音乐|歌手|MV/.test(x.name)).slice(0, 12)
    .map((x) => ({ id: x.id, name: x.name, picUrl: x.coverImgUrl, sub: x.updateFrequency }));
}
async function loadCat(c: string) {
  loading.value = true;
  try {
    const p = await api.topPlaylists(c, 24);
    playlists.value = p.map((x) => ({
      id: x.id, name: x.name, picUrl: x.coverImgUrl,
      sub: x.playCount ? `${Math.round(x.playCount / 10000)} 万次播放` : "",
    }));
  } finally { loading.value = false; }
}
onMounted(async () => {
  void loadTop();
  const a = await api.newAlbums(12);
  albums.value = a.map((x) => ({ id: x.id, name: x.name, picUrl: x.picUrl, sub: x.artist?.name }));
  await loadCat(cat.value);
});
function pick(c: string) { cat.value = c; void loadCat(c); }
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>发现</h1>
      <p>排行榜、分类歌单与新碟</p>
    </header>

    <Section v-if="toplists.length" title="排行榜">
      <CardGrid :items="toplists" :min="150" @open="(id) => router.push(`/playlist/${id}`)" />
    </Section>

    <Section title="分类歌单">
      <div class="cats">
        <button v-for="c in CATS" :key="c" :class="{ on: cat === c }" @click="pick(c)">{{ c }}</button>
      </div>
      <p v-if="loading" class="tip">加载中…</p>
      <CardGrid v-else :items="playlists" @open="(id) => router.push(`/playlist/${id}`)" />
    </Section>

    <Section v-if="albums.length" title="新碟上架">
      <CardGrid :items="albums" :min="150" @open="(id) => router.push(`/album/${id}`)" />
    </Section>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 2px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.cats { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 14px; }
.cats button { padding: 5px 13px; border-radius: 15px; background: var(--fill); font-size: 12.5px; color: var(--fg2); }
.cats button.on { background: var(--acc); color: #fff; font-weight: 600; }
.tip { padding: 14px 0; color: var(--fg2); font-size: 13px; }
@media (max-width: 640px) { .hero { padding: 16px 14px 0; } .hero h1 { font-size: 24px; } }
</style>
