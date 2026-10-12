<script setup lang="ts">
import Cover from "./Cover.vue";

defineProps<{
  items: { id: number; name: string; picUrl?: string; sub?: string }[];
  min?: number;
}>();
const emit = defineEmits<{ (e: "open", id: number): void }>();
</script>

<template>
  <div class="grid" :style="{ '--min': (min || 170) + 'px' }">
    <div v-for="it in items" :key="it.id" class="card" @click="emit('open', it.id)">
      <Cover :src="it.picUrl" :alt="it.name" radius="8px" class="cv" />
      <div class="tt clamp2">{{ it.name }}</div>
      <div v-if="it.sub" class="st ellipsis">{{ it.sub }}</div>
    </div>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--min), 1fr)); gap: 18px; }
.card { cursor: pointer; min-width: 0; }
.cv { box-shadow: 0 3px 12px rgba(0,0,0,.10); transition: transform .18s ease, box-shadow .18s ease; }
.card:hover .cv { transform: translateY(-3px); box-shadow: 0 10px 24px rgba(0,0,0,.16); }
.tt { margin-top: 9px; font-size: 13px; font-weight: 500; letter-spacing: -.01em; line-height: 1.3;
      min-height: 2.6em; }   /* 固定两行高度，避免长短标题导致卡片高矮不齐 */
.st { font-size: 12.5px; color: var(--fg2); margin-top: 1px; }
@media (max-width: 640px) {
  .grid { gap: 12px; }
  .tt { font-size: 12.5px; }
  .st { font-size: 11.5px; }
}
</style>
