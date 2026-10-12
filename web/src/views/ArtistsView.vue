<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { MicVocal } from "lucide-vue-next";
import { api } from "@/api/client";
import type { ArtistItem } from "@/api/types";
import Section from "@/components/Section.vue";

const router = useRouter();

/** 地区与性别筛选（与 /artist/list 的 area/type 参数一一对应） */
const AREAS: { label: string; v: number }[] = [
  { label: "全部", v: -1 },
  { label: "华语", v: 7 },
  { label: "欧美", v: 96 },
  { label: "日本", v: 8 },
  { label: "韩国", v: 16 },
];
const TYPES: { label: string; v: number }[] = [
  { label: "全部", v: -1 },
  { label: "男歌手", v: 1 },
  { label: "女歌手", v: 2 },
  { label: "乐队组合", v: 3 },
];

const area = ref(-1);
const type = ref(-1);
const list = ref<ArtistItem[]>([]);
const loading = ref(true);
const err = ref("");

async function load() {
  loading.value = true;
  err.value = "";
  try {
    list.value = await api.artistList(area.value, type.value, 60);
    if (!list.value.length) err.value = "这个筛选组合暂无歌手数据";
  } catch (e) {
    err.value = e instanceof Error ? e.message : "歌手数据加载失败";
  } finally {
    loading.value = false;
  }
}
function pickArea(v: number) { area.value = v; void load(); }
function pickType(v: number) { type.value = v; void load(); }
onMounted(load);
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>歌手</h1>
      <p>按地区与性别浏览热门歌手，点进歌手页听最热作品</p>
    </header>

    <div class="filters">
      <div class="row">
        <span class="lbl">地区</span>
        <button v-for="a in AREAS" :key="'a' + a.v" :class="{ on: area === a.v }" @click="pickArea(a.v)">
          {{ a.label }}
        </button>
      </div>
      <div class="row">
        <span class="lbl">类型</span>
        <button v-for="t in TYPES" :key="'t' + t.v" :class="{ on: type === t.v }" @click="pickType(t.v)">
          {{ t.label }}
        </button>
      </div>
    </div>

    <Section :title="`共 ${list.length} 位歌手`">
      <p v-if="loading" class="tip">加载中…</p>
      <p v-else-if="err" class="tip">{{ err }}</p>
      <div v-else class="grid">
        <div v-for="a in list" :key="a.id" class="card" @click="router.push(`/artist/${a.id}`)">
          <div class="av">
            <img v-if="a.picUrl" :src="a.picUrl" :alt="a.name" loading="lazy" />
            <span v-else class="ph"><MicVocal :size="26" /></span>
          </div>
          <div class="nm ellipsis">{{ a.name }}</div>
          <div class="sub ellipsis">
            {{ (a.alias && a.alias[0]) || (a.musicSize ? `${a.musicSize} 首歌` : "") }}
          </div>
        </div>
      </div>
    </Section>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 2px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.filters { padding: 14px 22px 4px; display: flex; flex-direction: column; gap: 8px; }
.row { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.lbl { font-size: 12.5px; color: var(--fg3); width: 30px; flex: none; }
.row button { font-size: 12.5px; padding: 4px 11px; border-radius: 14px; background: var(--fill);
              color: var(--fg2); }
.row button.on { background: var(--acc); color: #fff; }
.tip { font-size: 13px; color: var(--fg2); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(112px, 1fr)); gap: 18px 14px; }
.card { cursor: pointer; min-width: 0; text-align: center; }
.av { position: relative; width: 100%; aspect-ratio: 1; border-radius: 50%; overflow: hidden;
      background: var(--fill); box-shadow: 0 3px 12px rgba(0, 0, 0, .10);
      transition: transform .18s ease, box-shadow .18s ease; }
.card:hover .av { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(0, 0, 0, .16); }
.av img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ph { position: absolute; inset: 0; display: grid; place-items: center; color: var(--fg3); }
.nm { margin-top: 9px; font-size: 13px; font-weight: 500; letter-spacing: -.01em; }
.sub { font-size: 12px; color: var(--fg2); margin-top: 1px; min-height: 1.2em; }
@media (max-width: 640px) {
  .hero { padding: 16px 16px 2px; }
  .filters { padding: 10px 16px 0; }
  .grid { grid-template-columns: repeat(auto-fill, minmax(94px, 1fr)); gap: 14px 10px; }
}
</style>
