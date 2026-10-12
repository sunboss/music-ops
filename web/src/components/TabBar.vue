<script setup lang="ts">
import { House, Compass, Library, Sparkles } from "lucide-vue-next";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();
const tabs = [
  { to: "/", icon: House, label: "首页" },
  { to: "/explore", icon: Compass, label: "发现" },
  { to: "/library", icon: Library, label: "音乐库" },
  { to: "/ai", icon: Sparkles, label: "AI" },
];
const active = (to: string) => (to === "/" ? route.path === "/" : route.path.startsWith(to));
</script>

<template>
  <nav class="tabs vibrant safe-b">
    <a v-for="t in tabs" :key="t.to" :class="{ on: active(t.to) }" @click.prevent="router.push(t.to)">
      <component :is="t.icon" :size="21" :stroke-width="active(t.to) ? 2.4 : 1.9" />
      <span>{{ t.label }}</span>
    </a>
  </nav>
</template>

<style scoped>
.tabs { display: flex; padding: 7px 6px 6px; border-top: 1px solid var(--hair); }
a { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 3px 0 2px;
    font-size: 10.5px; color: var(--fg3); cursor: pointer; }
a.on { color: var(--acc); }
</style>
