<script setup lang="ts">
import { computed } from "vue";
import { X, Trash2, GripVertical } from "lucide-vue-next";
import { usePlayerStore } from "@/stores/player";
import Cover from "./Cover.vue";

const p = usePlayerStore();
const upNext = computed(() => p.queue.slice(p.index + 1));
const artistOf = (s: { ar?: { name: string }[] }) => (s.ar || []).map((a) => a.name).join(", ");
function jump(id: number) {
  const i = p.queue.findIndex((s) => s.id === id);
  if (i >= 0) void p.playAt(i);
}
function clearAfter() {
  p.queue = p.queue.slice(0, p.index + 1);
}
</script>

<template>
  <Transition name="slide">
    <aside v-if="p.showQueue" class="qd">
      <header>
        <div><b>播放队列</b><span>{{ p.queue.length }} 首</span></div>
        <button class="ib" @click="p.showQueue = false"><X :size="18" /></button>
      </header>

      <div v-if="p.current" class="now">
        <div class="lbl">正在播放</div>
        <div class="item on">
          <Cover :src="p.current.al?.picUrl" radius="5px" class="cv" />
          <div class="mm"><div class="nm ellipsis">{{ p.current.name }}</div>
            <div class="ar ellipsis">{{ artistOf(p.current) }}</div></div>
        </div>
      </div>

      <div class="list no-scrollbar">
        <div v-if="upNext.length" class="lbl">接下来 · {{ upNext.length }} 首
          <button class="clr" @click="clearAfter"><Trash2 :size="12" />清空</button>
        </div>
        <div v-for="s in upNext" :key="s.id" class="item" @click="jump(s.id)">
          <GripVertical :size="13" class="grip" />
          <Cover :src="s.al?.picUrl" radius="5px" class="cv" />
          <div class="mm">
            <div class="nm ellipsis">{{ s.name }}</div>
            <div class="ar ellipsis">{{ artistOf(s) }}</div>
          </div>
        </div>
        <p v-if="!p.queue.length" class="empty">队列是空的</p>
      </div>
    </aside>
  </Transition>
</template>

<style scoped>
.qd { position: fixed; top: 0; right: 0; bottom: 0; width: min(92vw, 360px); z-index: 70;
      background: var(--bg-elev); border-left: 1px solid var(--hair); display: flex; flex-direction: column;
      box-shadow: -18px 0 50px rgba(0,0,0,.22); }
header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px 10px;
         border-bottom: 0.5px solid var(--hair); }
header b { font-size: 15px; font-weight: 600; }
header span { font-size: 12px; color: var(--fg2); margin-left: 8px; }
.ib { width: 30px; height: 30px; display: grid; place-items: center; color: var(--fg2); border-radius: 50%; }
.ib:hover { background: var(--fill); }
.now { padding: 10px 8px 2px; }
.lbl { display: flex; align-items: center; justify-content: space-between; font-size: 11.5px; color: var(--fg3);
       letter-spacing: .04em; padding: 4px 10px 6px; }
.clr { display: inline-flex; align-items: center; gap: 4px; font-size: 11.5px; color: var(--fg2); }
.list { flex: 1; overflow-y: auto; padding: 0 8px 20px; }
.item { display: flex; align-items: center; gap: 10px; padding: 7px 8px; border-radius: 8px; cursor: pointer; }
.item:hover { background: var(--fill); }
.item.on { background: var(--acc-weak); cursor: default; }
.grip { color: var(--fg3); flex: none; }
.cv { width: 38px; flex: none; }
.mm { flex: 1; min-width: 0; }
.nm { font-size: 13.5px; font-weight: 500; }
.ar { font-size: 12px; color: var(--fg2); }
.empty { padding: 24px 12px; color: var(--fg2); font-size: 13px; }
@media (max-width: 900px) { .qd { width: 100vw; border-left: 0; } }
.slide-enter-active, .slide-leave-active { transition: transform .26s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
