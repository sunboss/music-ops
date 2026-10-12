<script setup lang="ts">
import { computed } from "vue";
import { Pause, Play, SkipForward } from "lucide-vue-next";
import { usePlayerStore } from "@/stores/player";
import Cover from "./Cover.vue";

const p = usePlayerStore();
const pct = computed(() => (p.duration ? Math.min(100, (p.progress / p.duration) * 100) : 0));
const artist = computed(() => (p.current?.ar || []).map((a) => a.name).join(", "));
</script>

<template>
  <div v-if="p.current" class="mini vibrant" @click="p.showFull = true">
    <div class="line"><i :style="{ width: pct + '%' }" /></div>
    <Cover :src="p.current.al?.picUrl" radius="5px" class="cv" />
    <div class="mm">
      <div class="nm ellipsis">{{ p.current.name }}</div>
      <div class="ar ellipsis">{{ artist }}</div>
    </div>
    <button class="bt" @click.stop="p.toggle()">
      <Pause v-if="p.playing" :size="19" fill="currentColor" />
      <Play v-else :size="19" fill="currentColor" />
    </button>
    <button class="bt" @click.stop="p.next()"><SkipForward :size="16" fill="currentColor" /></button>
  </div>
</template>

<style scoped>
.mini { position: relative; margin: 0 8px 6px; padding: 7px 9px; border-radius: 11px; border: 1px solid var(--hair);
        display: flex; align-items: center; gap: 10px; box-shadow: 0 6px 20px rgba(0,0,0,.13); overflow: hidden; }
.line { position: absolute; left: 0; right: 0; top: 0; height: 2px; background: var(--fill); }
.line i { display: block; height: 100%; background: var(--fg); opacity: .45; }
.cv { width: 36px; flex: none; }
.mm { flex: 1; min-width: 0; }
.nm { font-size: 13px; font-weight: 500; }
.ar { font-size: 11.5px; color: var(--fg2); }
.bt { width: 32px; height: 32px; display: grid; place-items: center; }
</style>
