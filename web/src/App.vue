<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterView, useRouter, useRoute } from "vue-router";
import { Search, Sparkles, House, Compass, Library, ChevronLeft } from "lucide-vue-next";
import PlayerBar from "@/components/PlayerBar.vue";
import MiniPlayer from "@/components/MiniPlayer.vue";
import TabBar from "@/components/TabBar.vue";
import { usePlayerStore } from "@/stores/player";

const router = useRouter();
const route = useRoute();
const p = usePlayerStore();
const kw = ref("");

const navs = [
  { to: "/", label: "首页", icon: House },
  { to: "/explore", label: "发现", icon: Compass },
  { to: "/library", label: "音乐库", icon: Library },
  { to: "/ai", label: "AI 音乐", icon: Sparkles },
];
const isActive = (to: string) => (to === "/" ? route.path === "/" : route.path.startsWith(to));

/** 顶栏标题：首页不显示（页面内已有大标题），二级页显示类型名 */
const pageTitle = computed(() => {
  const p = route.path;
  if (p === "/") return "";
  if (p.startsWith("/playlist")) return "歌单";
  if (p.startsWith("/album")) return "专辑";
  if (p.startsWith("/artist")) return "歌手";
  if (p.startsWith("/search")) return "搜索";
  if (p.startsWith("/daily")) return "每日推荐";
  if (p.startsWith("/explore")) return "发现";
  if (p.startsWith("/library")) return "音乐库";
  if (p.startsWith("/ai")) return "AI 音乐";
  if (p.startsWith("/settings")) return "设置";
  return "";
});

function doSearch() {
  const q = kw.value.trim();
  if (q) router.push(`/search/${encodeURIComponent(q)}`);
}
</script>

<template>
  <div class="shell">
    <!-- 桌面侧栏 -->
    <aside class="side">
      <div class="brand" @click="router.push('/')">
        <div class="mk" /><b>R-Music</b>
      </div>
      <a v-for="n in navs" :key="n.to" class="nv" :class="{ on: isActive(n.to) }" @click="router.push(n.to)">
        <component :is="n.icon" :size="17" :stroke-width="isActive(n.to) ? 2.3 : 1.9" />
        <span>{{ n.label }}</span>
      </a>
      <div class="sh">播放队列</div>
      <div class="qn">{{ p.hasQueue ? `${p.queue.length} 首 · 第 ${p.index + 1} 首` : "空" }}</div>
    </aside>

    <div class="main">
      <!-- 顶栏 -->
      <header class="top vibrant">
        <button v-if="route.name !== 'home'" class="back" @click="router.back()">
          <ChevronLeft :size="20" />
        </button>
        <div class="tb-title ellipsis">{{ pageTitle }}</div>
        <div class="search">
          <Search :size="15" />
          <input v-model="kw" placeholder="搜索歌曲 / 歌手 / 歌单" @keydown.enter="doSearch" />
        </div>
      </header>

      <div class="scroll no-scrollbar">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </div>

      <!-- 桌面播放条 -->
      <PlayerBar class="d-bar" />
      <!-- 移动端：迷你播放条 + 底部 Tab -->
      <div class="m-bottom vibrant">
        <MiniPlayer />
        <TabBar />
      </div>
    </div>
  </div>
</template>

<style scoped>
.shell { display: flex; height: 100%; background: var(--bg); }
.side { display: none; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; height: 100%; }
.top { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--hair); flex: none; }
.back { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; color: var(--fg2); }
.back:hover { background: var(--fill); }
.tb-title { font-size: 15px; font-weight: 600; letter-spacing: -.015em; }
.search { margin-left: auto; display: flex; align-items: center; gap: 7px; width: min(46vw, 260px);
          padding: 6px 10px; border-radius: 16px; background: var(--fill); color: var(--fg2); }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font-size: 13px; color: var(--fg); }
.scroll { flex: 1; overflow-y: auto; overflow-x: hidden; -webkit-overflow-scrolling: touch; }
.d-bar { display: none; }
.m-bottom { flex: none; padding-top: 4px; }
.m-bottom :deep(.mini) { margin-bottom: 2px; }

/* 桌面：固定侧栏 + 底部播放条 */
@media (min-width: 1024px) {
  .side { display: block; width: var(--sb-w); flex: none; background: var(--side);
          backdrop-filter: saturate(180%) blur(20px); border-right: 1px solid var(--hair); padding: 14px 10px; }
  .brand { display: flex; align-items: center; gap: 8px; padding: 6px 8px 16px; cursor: pointer; }
  .brand b { font-size: 14px; letter-spacing: -.01em; }
  .mk { width: 22px; height: 22px; border-radius: 6px; background: linear-gradient(135deg, #7b78e8, var(--acc)); }
  .nv { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 7px; font-size: 13.5px;
        color: var(--fg); cursor: pointer; margin-bottom: 1px; letter-spacing: -.01em; }
  .nv:hover { background: var(--fill); }
  .nv.on { background: var(--acc-weak); color: var(--acc); font-weight: 500; }
  .sh { font-size: 11px; color: var(--fg3); padding: 18px 10px 5px; letter-spacing: .04em; }
  .qn { font-size: 12.5px; color: var(--fg2); padding: 0 10px; }
  .d-bar { display: flex; }
  .m-bottom { display: none; }
  .search { width: 300px; }
}
/* 手机端不显示顶栏标题：页面内的大标题已经足够，省出横向空间给搜索 */
@media (max-width: 1023px) {
  .tb-title { display: none; }
}
</style>
