<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import Section from "@/components/Section.vue";
import CardGrid from "@/components/CardGrid.vue";

const router = useRouter();
const loading = ref(true);
const err = ref("");
const recos = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);
const albums = ref<{ id: number; name: string; picUrl?: string; sub?: string }[]>([]);

onMounted(async () => {
  try {
    const [p, a] = await Promise.all([api.personalized(12), api.newAlbums(10)]);
    recos.value = p.map((x) => ({ ...x, sub: x.playCount ? `${Math.round(x.playCount / 10000)} 万次播放` : "" }));
    albums.value = a.map((x) => ({ id: x.id, name: x.name, picUrl: x.picUrl, sub: x.artist?.name }));
  } catch (e) {
    err.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
});

const today = new Date();
const dateStr = `${today.getMonth() + 1}月${today.getDate()}日`;
</script>

<template>
  <div class="page">
    <header class="hero">
      <h1>为你推荐</h1>
      <p>{{ dateStr }} · 依据你的收听更新</p>
    </header>

    <div class="quick">
      <button class="qc" @click="router.push('/daily/songs')">
        <span class="big">每日推荐</span><span class="sm">按口味生成</span>
      </button>
      <button class="qc ai" @click="router.push('/ai')">
        <span class="big">AI 点歌</span><span class="sm">一句话生成歌单</span>
      </button>
    </div>

    <p v-if="err" class="err">加载失败：{{ err }}</p>
    <Section v-if="loading" title="推荐歌单"><div class="sk-row" /></Section>
    <Section v-else title="推荐歌单" more="查看全部" @more="router.push('/explore')">
      <CardGrid :items="recos" @open="(id) => router.push(`/playlist/${id}`)" />
    </Section>

    <Section v-if="!loading && albums.length" title="新碟上架">
      <CardGrid :items="albums" :min="140" @open="(id) => router.push(`/album/${id}`)" />
    </Section>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 6px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.quick { display: flex; gap: 12px; padding: 16px 22px 2px; }
.qc { flex: 1; text-align: left; padding: 14px 16px; border-radius: 12px; background: var(--fill); }
.qc .big { display: block; font-size: 15px; font-weight: 600; letter-spacing: -.015em; }
.qc .sm { font-size: 12px; color: var(--fg2); }
.qc.ai { background: var(--acc-weak); }
.qc.ai .big { color: var(--acc); }
.err { padding: 12px 22px; color: #ff453a; font-size: 13px; }
.sk-row { height: 170px; border-radius: 10px; background: var(--fill); }
@media (max-width: 640px) {
  .hero { padding: 16px 14px 4px; }
  .hero h1 { font-size: 24px; }
  .quick { padding: 12px 14px 0; }
  .qc { padding: 12px 13px; }
}
</style>
