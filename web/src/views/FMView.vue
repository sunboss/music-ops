<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Play, Pause, SkipForward, Heart, ThumbsDown, Radio } from "lucide-vue-next";
import { api } from "@/api/client";
import type { Song } from "@/api/types";
import Cover from "@/components/Cover.vue";
import { usePlayerStore } from "@/stores/player";

const p = usePlayerStore();
const loading = ref(false);
const liked = ref<number[]>(JSON.parse(localStorage.getItem("fmLiked") || "[]"));
const dislike = ref(0);

const cur = computed(() => p.current);
const artist = computed(() => (cur.value?.ar || []).map((a) => a.name).join(", "));

/**
 * 私人 FM 续歌：匿名访问时网易云每次只返回 1 首，所以要多批凑够队列，
 * 否则「不感兴趣」会因为没有下一首而重播同一首。
 */
const TARGET = 8;          // 队列里保持至少这么多首待播
async function more(force = false) {
  if (loading.value) return;
  loading.value = true;
  try {
    const have = () => p.queue.length - p.index - 1;
    let attempts = 0;
    while ((force || have() < TARGET - 1) && attempts < 12) {
      attempts++;
      const list = await api.personalFm();
      const fresh = list.filter((s) => s.id && !p.queue.some((q) => q.id === s.id));
      if (!fresh.length) break;
      const empty = p.queue.length === 0;
      p.queue = [...p.queue, ...fresh];
      if (empty) void p.playAt(0);
      if (have() >= TARGET) break;
    }
  } finally { loading.value = false; }
}

watch(() => p.index, (i) => { if (i >= 0 && p.queue.length - i - 1 < 2) void more(); });

function like() {
  if (!cur.value) return;
  liked.value = [cur.value.id, ...liked.value.filter((x) => x !== cur.value!.id)].slice(0, 500);
  localStorage.setItem("fmLiked", JSON.stringify(liked.value));
  void api.reportTaste(cur.value.id, "play", p.duration || 0, p.duration || 0);   // 明确喜欢 -> 记为常听
  p.next();
}
async function nah() {
  dislike.value++;
  // 先确保有下一首：匿名 FM 每次只返回 1 首，直接 next() 会因为没有后继而重播本首
  if (p.index + 1 >= p.queue.length) await more(true);
  if (p.index + 1 < p.queue.length) p.next();
  else p.toggle();                     // 实在拿不到新歌就暂停，而不是假装切歌
}

onMounted(() => { if (!p.hasQueue) void more(); else if (!p.playing) p.toggle();
  if (p.hasQueue) void more();          // 已有队列也补一下，保证有后继可播
});
</script>

<template>
  <div class="page">
    <header class="hero">
      <div class="badge"><Radio :size="14" />私人 FM</div>
      <h1>为你持续播</h1>
      <p>不喜欢就划走，听满 30 秒的会被记住</p>
    </header>

    <div v-if="cur" class="card">
      <Cover :src="cur.al?.picUrl" :alt="cur.name" radius="12px" class="big" eager />
      <div class="nm">{{ cur.name }}</div>
      <div class="ar">{{ artist }}</div>
      <div class="ctl">
        <button class="ib no" title="不感兴趣" @click="nah"><ThumbsDown :size="20" /></button>
        <button class="ib play" @click="p.toggle()">
          <Pause v-if="p.playing" :size="26" fill="currentColor" />
          <Play v-else :size="26" fill="currentColor" />
        </button>
        <button class="ib" :class="{ on: liked.includes(cur.id) }" title="喜欢" @click="like">
          <Heart :size="20" :fill="liked.includes(cur.id) ? 'currentColor' : 'none'" />
        </button>
      </div>
      <button class="skip" @click="p.next()"><SkipForward :size="14" />换一首</button>
      <p class="stat">已听 {{ p.index + 1 }} 首 · 队列还有 {{ Math.max(0, p.queue.length - p.index - 1) }} 首<template v-if="dislike"> · 跳过 {{ dislike }} 首</template></p>
    </div>
    <p v-else class="tip">{{ loading ? "正在为你挑选…" : "暂时拿不到 FM 数据，稍后重试；也可以直接用「AI 音乐」一句话生成电台。" }}</p>
    <div style="height: 24px" />
  </div>
</template>

<style scoped>
.page { padding-bottom: 24px; }
.hero { padding: 22px 22px 8px; }
.badge { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600;
         color: var(--acc); background: var(--acc-weak); padding: 3px 10px; border-radius: 12px; }
.hero h1 { font-size: 27px; font-weight: 700; letter-spacing: -.022em; margin-top: 8px; }
.hero p { margin: 3px 0 0; font-size: 13px; color: var(--fg2); }
.card { display: grid; justify-items: center; gap: 8px; padding: 18px 22px 0; }
.big { width: min(46vw, 300px); box-shadow: 0 16px 44px rgba(0,0,0,.2); }
.nm { font-size: 20px; font-weight: 700; letter-spacing: -.02em; margin-top: 12px; text-align: center; }
.ar { font-size: 13.5px; color: var(--fg2); }
.ctl { display: flex; align-items: center; gap: 24px; margin-top: 12px; }
.ib { width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--fg); }
.ib:hover { background: var(--fill); }
.ib.on { color: #ff453a; }
.ib.play { width: 60px; height: 60px; background: var(--acc); color: #fff; }
.ib.no { color: var(--fg2); }
.skip { display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; font-size: 13px; color: var(--fg2); }
.stat { font-size: 12px; color: var(--fg3); margin: 6px 0 0; }
.tip { padding: 30px 22px; color: var(--fg2); font-size: 13px; max-width: 520px; line-height: 1.7; }
@media (max-width: 640px) { .hero { padding: 16px 14px 6px; } .hero h1 { font-size: 24px; } .card { padding: 12px 14px 0; } }
</style>
