<script setup lang="ts">
import { Construction } from "lucide-vue-next";
defineProps<{ title?: string }>();
</script>

<template>
  <div class="ph">
    <Construction :size="30" />
    <h2>每日推荐</h2>
    <p>该页面在后续阶段实现（P1/P2）。当前阶段先交付：首页、歌单、AI 音乐、播放器。</p>
  </div>
</template>

<style scoped>
.ph { display: grid; place-items: center; gap: 8px; padding: 90px 24px; color: var(--fg2); text-align: center; }
h2 { font-size: 19px; font-weight: 700; color: var(--fg); }
p { font-size: 13px; max-width: 380px; margin: 0; }
</style>
