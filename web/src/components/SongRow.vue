<script setup lang="ts">
import { computed } from "vue";
import { Play } from "lucide-vue-next";
import type { Song } from "@/api/types";
import Cover from "./Cover.vue";

const props = defineProps<{ song: Song; index: number; active?: boolean; showAlbum?: boolean }>();
const emit = defineEmits<{ (e: "play", i: number): void }>();

const artist = computed(() => (props.song.ar || []).map((a) => a.name).join(", "));
const album = computed(() => props.song.al?.name || "");
const time = computed(() => {
  const s = Math.round((props.song.dt || 0) / 1000);
  return s ? `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}` : "--:--";
});
const dead = computed(() => props.song.playable === false);
</script>

<template>
  <div class="row group" :class="{ on: props.active, dead }" @dblclick="!dead && emit('play', props.index)">
    <div class="ix tnum">
      <span v-if="props.active" class="pl">♪</span>
      <span v-else class="n">{{ props.index + 1 }}</span>
      <button class="pv" :disabled="dead" @click.stop="emit('play', props.index)">
        <Play :size="14" fill="currentColor" />
      </button>
    </div>
    <div class="thumb"><Cover :src="props.song.al?.picUrl" :alt="props.song.name" radius="6px" /></div>
    <div class="mm">
      <div class="nm ellipsis">{{ props.song.name }}</div>
      <!-- 手机端：歌手 + 专辑并入副标题（不再把专辑挤成 “THE…”） -->
      <div class="ar ellipsis">
        {{ artist }}<span v-if="props.showAlbum && album" class="al-m"> · {{ album }}</span>
      </div>
    </div>
    <div v-if="props.showAlbum" class="ab ellipsis">{{ album }}</div>
    <div class="du tnum">{{ dead ? "无音源" : time }}</div>
  </div>
</template>

<style scoped>
.row { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-radius: 8px; cursor: default;
       border-bottom: 0.5px solid var(--hair); }
.row:hover { background: var(--fill); }
.row.on { background: var(--acc-weak); border-bottom-color: transparent; }
.row.dead { opacity: .45; }
.ix { width: 20px; flex: none; text-align: center; font-size: 13px; color: var(--fg3); position: relative; }
.row.on .ix { color: var(--acc); }
.ix .pv { display: none; position: absolute; inset: 0; align-items: center; justify-content: center; color: var(--fg); }
.row:hover .ix .n, .row:hover .ix .pl { visibility: hidden; }
.row:hover .ix .pv { display: flex; }
.thumb { width: 42px; flex: none; }
.mm { flex: 1; min-width: 0; }
.nm { font-size: 14.5px; font-weight: 500; letter-spacing: -.012em; }
.ar { font-size: 12.5px; color: var(--fg2); }
.ab { width: 26%; font-size: 13px; color: var(--fg2); }
.du { width: 44px; flex: none; text-align: right; font-size: 12.5px; color: var(--fg3); }
/* 手机端：专辑并入副标题（.al-m 显示），独立的专辑列（.ab）隐藏，
   避免像旧站那样把专辑名截成 “THE…” */
.al-m { display: none; }
@media (max-width: 640px) {
  .row { padding: 8px 10px; gap: 10px; }
  .thumb { width: 44px; }
  .ab { display: none; }
  .al-m { display: inline; }
  .du { width: 46px; }
}
</style>
