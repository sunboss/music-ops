<script setup lang="ts">
import { computed } from "vue";
import { Pause, Play, SkipBack, SkipForward, Sparkles, Cast, Heart } from "lucide-vue-next";
import { isFav, toggleFav } from "@/utils/favorites";
import { computed as vueComputed } from "vue";
import CastMenu from "./CastMenu.vue";
import { usePlayerStore } from "@/stores/player";
import { useRouter } from "vue-router";
import Cover from "./Cover.vue";

const p = usePlayerStore();
const router = useRouter();
const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const pct = computed(() => (p.duration ? Math.min(100, (p.progress / p.duration) * 100) : 0));
const artist = computed(() => (p.current?.ar || []).map((a) => a.name).join(", "));

const liked = vueComputed(() => isFav(p.current?.id));
function like() { toggleFav(p.current); }

function seek(e: MouseEvent) {
  const el = e.currentTarget as HTMLElement;
  p.seekRatio((e.clientX - el.getBoundingClientRect().left) / el.getBoundingClientRect().width);
}
</script>

<template>
  <div class="bar vibrant">
    <!-- Apple Music 标志性的顶部细进度线 -->
    <div class="track" @click="seek"><i :style="{ width: pct + '%' }" /></div>
    <Cover v-if="p.current" :src="p.current.al?.picUrl" radius="6px" class="pc" @click="p.showFull = true" />
    <div v-else class="pc empty" />
    <div class="meta" @click="p.current && (p.showFull = true)">
      <div class="nm ellipsis">{{ p.current?.name || "未在播放" }}</div>
      <div class="ar ellipsis">{{ artist || "选一首歌开始" }}</div>
    </div>
    <button class="bt" @click="p.prev()" :disabled="!p.hasQueue"><SkipBack :size="17" fill="currentColor" /></button>
    <button class="bt big" @click="p.toggle()" :disabled="!p.hasQueue">
      <Pause v-if="p.playing" :size="21" fill="currentColor" />
      <Play v-else :size="21" fill="currentColor" />
    </button>
    <button class="bt" @click="p.next()" :disabled="!p.hasQueue"><SkipForward :size="17" fill="currentColor" /></button>
    <div class="sp" />
    <button class="heart" :class="{ on: liked }" :title="liked ? '取消喜欢' : '喜欢（会影响 AI 推荐）'"
            @click="like" :disabled="!p.current">
      <Heart :size="15" :fill="liked ? 'currentColor' : 'none'" />
    </button>
    <div class="tm tnum">{{ fmt(p.progress) }} / {{ fmt(p.duration) }}</div>
    <!-- 投屏：直接弹设备勾选（Safari 走系统列表），不弹页面 -->
    <button class="cast" :class="{ on: !!p.castName }"
            :title="p.castName ? '正在投屏到 ' + p.castName + '（点击可停止/换设备）' : '投屏到音箱 / 电视'"
            @click="p.quickCast()">
      <Cast :size="15" /><span v-if="p.castName" class="cn ellipsis">{{ p.castName }}</span>
    </button>
    <button class="ai" title="AI 一句话点歌" @click="router.push('/ai')"><Sparkles :size="14" /></button>
  </div>
  <CastMenu v-if="p.showCast" />
  <Transition name="toast">
    <div v-if="p.toast" class="toast">{{ p.toast }}</div>
  </Transition>
</template>

<style scoped>
.bar { position: relative; display: flex; align-items: center; gap: 13px; height: var(--bar-h); padding: 0 18px;
       border-top: 1px solid var(--hair); }
.track { position: absolute; left: 0; right: 0; top: -1px; height: 3px; cursor: pointer; }
.track i { display: block; height: 100%; background: var(--fg); opacity: .5; transition: width .25s linear; }
.track:hover { height: 5px; }
.pc { width: 44px; flex: none; box-shadow: var(--shadow); cursor: pointer; }
.meta { cursor: pointer; }
.pc.empty { background: var(--fill); aspect-ratio: 1; }
.pc :deep(img) { border-radius: 6px; }
.meta { min-width: 120px; max-width: 240px; }
.nm { font-size: 13px; font-weight: 500; letter-spacing: -.01em; }
.ar { font-size: 12px; color: var(--fg2); }
.toast { position: fixed; left: 50%; transform: translateX(-50%); bottom: calc(var(--bar-h) + 16px);
         padding: 8px 16px; border-radius: 18px; background: var(--bg-elev); border: 0.5px solid var(--hair);
         box-shadow: var(--shadow); font-size: 12.5px; color: var(--fg); z-index: 70; max-width: 80vw; }
.toast-enter-active, .toast-leave-active { transition: opacity .18s, transform .18s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(6px); }
.heart { width: 30px; height: 30px; display: grid; place-items: center; color: var(--fg2); border-radius: 8px; }
.heart.on { color: #ff375f; }
.heart:disabled { opacity: .4; }
.cast { display: inline-flex; align-items: center; gap: 6px; max-width: 150px; padding: 5px 10px;
         border-radius: 14px; color: var(--fg2); }
.cast:hover { background: var(--fill); }
.cast.on { color: var(--acc); background: var(--acc-weak); }
.cast .cn { font-size: 12px; max-width: 110px; }
@media (max-width: 640px) { .cast .cn { display: none; } }
.bt { width: 30px; height: 30px; display: grid; place-items: center; color: var(--fg); opacity: .88; }
.bt:hover { opacity: 1; }
.bt.big { width: 36px; height: 36px; }
.bt:disabled { opacity: .3; }
.sp { flex: 1; }
.tm { font-size: 11.5px; color: var(--fg2); }
.ai { width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
      background: var(--acc); color: #fff; }
</style>
