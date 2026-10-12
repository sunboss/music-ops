<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Play, Sparkles } from "lucide-vue-next";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import SongRow from "@/components/SongRow.vue";
import { usePlayerStore } from "@/stores/player";

const p = usePlayerStore();
const songs = ref<Song[]>([]);
const loading = ref(true);
const err = ref("");

onMounted(async () => {
  try { songs.value = await api.dailySongs(); }
  catch (e) { err.value = e instanceof Error ? e.message : "加载失败"; }
  finally { loading.value = false; }
});

const today = new Date();
const label = computed(() => `${today.getMonth() + 1}月${today.getDate()}日`);
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>每日推荐</h1>
      <p>{{ label }} · 按你的收听口味生成</p>
    </header>
    <div class="ops">
      <button class="play" :disabled="!songs.length" @click="p.playQueue(songs, 0)">
        <Play :size="15" fill="currentColor" />播放全部
      </button>
      <button class="ghost" @click="$router.push('/ai')"><Sparkles :size="15" />让 AI 再配一张</button>
    </div>
    <p v-if="err" class="tip">加载失败：{{ err }}</p>
    <p v-else-if="loading" class="tip">正在为你挑选…</p>
    <p v-else-if="!songs.length" class="tip">今日推荐尚未生成（需要登录网易云账号后才有数据）</p>
    <div v-else class="list">
      <SongRow v-for="(s, i) in songs" :key="s.id" :song="s" :index="i" class="vrow"
               :active="p.current?.id === s.id" @play="(idx) => p.playQueue(songs, idx)" />
    </div>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 4px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.ops { display: flex; gap: 10px; padding: 14px 22px 4px; flex-wrap: wrap; }
.play { display: inline-flex; align-items: center; gap: 6px; padding: 8px 20px; border-radius: 20px;
        background: var(--acc); color: #fff; font-weight: 600; font-size: 13.5px; }
.ghost { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 20px;
         background: var(--fill); font-size: 13px; }
.tip { padding: 26px 22px; color: var(--fg2); font-size: 13px; }
.list { padding: 8px 10px 0; }
.vrow { content-visibility: auto; contain-intrinsic-size: 56px; }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 2px; } .hero h1 { font-size: 24px; }
  .ops { padding: 12px 14px 2px; } .list { padding: 6px 4px 0; }
}
</style>
