<script setup lang="ts">
import { ref } from "vue";

const props = withDefaults(defineProps<{
  src?: string; alt?: string; radius?: string; eager?: boolean;
}>(), { radius: "8px", eager: false });

const loaded = ref(false);
const failed = ref(false);
</script>

<template>
  <div class="cover" :style="{ borderRadius: props.radius }">
    <div v-if="!loaded" class="ph" />
    <img
      v-if="props.src && !failed"
      :src="props.src"
      :alt="props.alt || ''"
      :loading="props.eager ? 'eager' : 'lazy'"
      decoding="async"
      @load="loaded = true"
      @error="failed = true; loaded = true"
    />
    <div v-else-if="failed" class="ph ph-broken">♪</div>
  </div>
</template>

<style scoped>
.cover { position: relative; width: 100%; aspect-ratio: 1; overflow: hidden; background: var(--fill); }
.cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.ph { position: absolute; inset: 0; background: linear-gradient(110deg, var(--fill) 30%, rgba(120,120,128,.06) 50%, var(--fill) 70%);
      background-size: 200% 100%; animation: sh 1.4s linear infinite; }
.ph-broken { display: grid; place-items: center; font-size: 28px; color: var(--fg3); animation: none; }
@keyframes sh { from { background-position: 200% 0 } to { background-position: -200% 0 } }
</style>
