<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Cast, RefreshCw, X, Wifi, AlertTriangle, Square } from "lucide-vue-next";
import { haPlayers, haCast, haStop, haReady, haHint, type HaPlayer } from "@/utils/ha";
import { usePlayerStore } from "@/stores/player";
import { useRouter } from "vue-router";

const p = usePlayerStore();
const router = useRouter();
const list = ref<HaPlayer[]>([]);
const busy = ref(false);
const casting = ref("");
const err = ref("");
const loaded = ref(false);

async function load() {
  busy.value = true; err.value = "";
  try {
    list.value = await haPlayers();
    loaded.value = true;
  } catch (e) {
    err.value = haHint(e);
  } finally { busy.value = false; }
}

/** 投屏用的是我们自己的「一个 URL 就是一首歌」接口，HA 侧不需要任何模板 */
function streamUrl() {
  const id = p.current?.id;
  return id ? `${location.origin}/api/ma/play?id=${id}` : "";
}

async function cast(pl: HaPlayer) {
  if (!p.current) { err.value = "先播一首歌，再投屏"; return; }
  err.value = ""; casting.value = pl.entity_id;
  try {
    await haCast(pl.entity_id, streamUrl(), p.current.name);
    p.castEntity = pl.entity_id;
    p.castName = pl.name;
  } catch (e) {
    err.value = haHint(e);
    p.castEntity = ""; p.castName = "";
  } finally { casting.value = ""; }
}

async function stop() {
  if (!p.castEntity) return;
  try { await haStop(p.castEntity); } catch { /* 设备可能已停 */ }
  p.castEntity = ""; p.castName = "";
}

onMounted(() => { if (haReady()) void load(); });
</script>

<template>
  <div class="mask" @click.self="p.showCast = false">
    <div class="sheet">
      <header>
        <Cast :size="17" />
        <h2>投屏</h2>
        <span class="sp" />
        <button v-if="haReady()" class="ib" title="刷新设备" @click="load">
          <RefreshCw :size="15" :class="{ spin: busy }" />
        </button>
        <button class="ib" title="关闭" @click="p.showCast = false"><X :size="16" /></button>
      </header>

      <div v-if="p.castName" class="now">
        <Wifi :size="15" />
        <div>
          <b>正在投屏到 {{ p.castName }}</b>
          <span v-if="p.current">《{{ p.current.name }}》</span>
        </div>
        <button class="ghost" @click="stop"><Square :size="12" />停止</button>
      </div>

      <!-- 没配置：给一个明确的入口，不假装能用 -->
      <div v-if="!haReady()" class="empty">
        <p>投屏要先接上你家的 <b>Home Assistant</b>：设备都在你家里，而服务器在东京，够不到它们。</p>
        <p class="sub">去「设置 → 投屏」填 HA 地址与长期访问令牌（只存在你浏览器本地，不会发给服务器）。</p>
        <button class="go" @click="p.showCast = false; router.push('/settings')">去设置</button>
      </div>

      <p v-else-if="err" class="err"><AlertTriangle :size="14" />{{ err }}</p>

      <template v-else>
        <p v-if="busy && !list.length" class="sub pad">正在读取设备…</p>
        <p v-else-if="loaded && !list.length" class="sub pad">
          没读到播放器。HA 里要先有 Music Assistant（或 DLNA / Chromecast）集成，设备才会出现在这里。
        </p>
        <div v-else class="list">
          <button v-for="d in list" :key="d.entity_id" class="dev" :class="{ off: d.state === 'unavailable' }"
                  :disabled="casting === d.entity_id" @click="cast(d)">
            <Cast :size="16" />
            <div>
              <b>{{ d.name }}</b>
              <span>{{ d.state === "unavailable" ? "不可用" : d.state === "idle" ? "空闲" : d.state }}</span>
            </div>
            <i v-if="casting === d.entity_id" class="spin" />
            <i v-else-if="p.castEntity === d.entity_id" class="on">投屏中</i>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: flex-end;
        justify-content: center; z-index: 60; }
.sheet { width: 100%; max-width: 520px; background: var(--bg-elev); border-radius: 16px 16px 0 0;
         padding: 14px 16px 22px; max-height: 78vh; overflow: auto; box-shadow: var(--shadow); }
header { display: flex; align-items: center; gap: 9px; padding-bottom: 10px; border-bottom: 0.5px solid var(--hair); }
header h2 { font-size: 16px; font-weight: 600; }
header .sp { flex: 1; }
.ib { width: 30px; height: 30px; display: grid; place-items: center; color: var(--fg2); border-radius: 8px; }
.ib:hover { background: var(--fill); }
.now { display: flex; align-items: center; gap: 10px; padding: 12px 0; color: var(--acc); }
.now div { flex: 1; min-width: 0; }
.now b { display: block; font-size: 13.5px; }
.now span { font-size: 12px; color: var(--fg2); }
.ghost { display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: 14px;
         background: var(--fill); color: var(--fg); font-size: 12.5px; }
.empty { padding: 22px 4px 6px; }
.empty p { font-size: 13px; line-height: 1.6; color: var(--fg2); }
.empty .sub { margin-top: 8px; }
.go { margin-top: 14px; padding: 9px 20px; border-radius: 20px; background: var(--acc); color: #fff;
      font-weight: 600; font-size: 13.5px; }
.err { display: flex; gap: 7px; align-items: flex-start; white-space: pre-wrap; padding: 14px 0 4px;
       color: #ff9f0a; font-size: 12.5px; line-height: 1.55; }
.sub { font-size: 12.5px; color: var(--fg2); }
.pad { padding: 18px 2px; line-height: 1.6; }
.list { padding-top: 6px; }
.dev { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; padding: 11px 10px;
       border-radius: 10px; }
.dev:hover { background: var(--fill); }
.dev.off { opacity: .5; }
.dev div { flex: 1; min-width: 0; }
.dev b { display: block; font-size: 14px; font-weight: 500; }
.dev span { font-size: 12px; color: var(--fg2); }
.dev .on { font-size: 11.5px; color: var(--acc); font-style: normal; }
.spin { width: 13px; height: 13px; border: 2px solid var(--acc); border-top-color: transparent;
        border-radius: 50%; animation: sp .7s linear infinite; }
@keyframes sp { to { transform: rotate(360deg) } }
</style>
