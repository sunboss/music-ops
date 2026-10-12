<script setup lang="ts">
/**
 * 备用投屏小菜单（不是页面）：只有浏览器没有原生投屏能力、
 * 或投屏失败时才出现，直接列出发现到的设备供勾选。
 * Safari 的 AirPlay 走系统列表，根本不经过这里。
 */
import { onMounted, ref } from "vue";
import { Check, RefreshCw, Square, Cast } from "lucide-vue-next";
import { airplaySupported, remoteSupported } from "@/utils/cast";
import { bridgeState, dlnaDevices, dlnaCast, localNetworkPermission, type DlnaDevice } from "@/utils/cast";
import { haReady, haPlayers, haCast, haStop, haHint, type HaPlayer } from "@/utils/ha";
import { usePlayerStore } from "@/stores/player";

const p = usePlayerStore();
const dlna = ref<DlnaDevice[]>([]);
const ha = ref<HaPlayer[]>([]);
const busy = ref(false);
const err = ref("");
const blocked = ref(false);      // 小桥在跑但被浏览器的「本地网络访问」策略拦了

const canNative = airplaySupported() || remoteSupported();

function url() {
  return p.current?.id ? `${location.origin}/api/ma/play?id=${p.current.id}` : "";
}

async function scan() {
  busy.value = true; err.value = "";
  try {
    const st = await bridgeState();
    blocked.value = st === "blocked";
    if (st === "ok") {
      try { dlna.value = await dlnaDevices(); } catch { dlna.value = []; }
    }
    if (haReady()) {
      try { ha.value = await haPlayers(); } catch (e) { err.value = haHint(e); }
    }
  } finally { busy.value = false; }
}

async function pickDlna(d: DlnaDevice) {
  if (!p.current) { p.flash("先播一首歌"); return; }
  try {
    await dlnaCast(d, url());
    p.castName = d.name; p.castMode = "dlna";
    p.showCast = false;
  } catch (e) { err.value = e instanceof Error ? e.message : String(e); }
}

async function pickHa(d: HaPlayer) {
  if (!p.current) { p.flash("先播一首歌"); return; }
  try {
    await haCast(d.entity_id, url(), p.current.name);
    p.castName = d.name; p.castMode = "ha"; p.castEntity = d.entity_id;
    p.showCast = false;
  } catch (e) { err.value = haHint(e); }
}

async function stop() {
  if (p.castMode === "ha" && p.castEntity) { try { await haStop(p.castEntity); } catch { /* 忽略 */ } }
  p.stopCastLocal();
  p.showCast = false;
}

/** 让浏览器弹出/重新询问「本地网络访问」权限（必须由点击触发） */
async function askLocalNetwork() {
  try { await fetch("http://127.0.0.1:8787/health", { cache: "no-store" }); } catch { /* 被拦也正常 */ }
  const perm = await localNetworkPermission();
  await scan();
  if (blocked.value) {
    err.value = perm === "denied"
      ? "浏览器仍拒绝访问本地网络：地址栏左侧「站点设置」→ 把「本地网络访问」改为允许"
      : "";
  }
}

/** 再弹一次系统设备列表（Safari 里就是带勾选的设备列表） */
async function systemPicker() {
  p.showCast = false;
  await p.quickCast();
}

onMounted(scan);
</script>

<template>
  <div class="wrap" @click.self="p.showCast = false">
    <div class="menu">
      <div v-if="p.castName" class="cur">
        <Check :size="14" />
        <span class="nm ellipsis">{{ p.castName }}</span>
        <button class="x" title="停止投屏" @click="stop"><Square :size="12" /></button>
      </div>

      <button v-if="canNative" class="row" @click="systemPicker">
        <Cast :size="14" /><span>系统设备列表（勾选设备）</span>
      </button>

      <div v-if="dlna.length" class="grp">
        <div class="hd">DLNA</div>
        <button v-for="d in dlna" :key="d.control || d.name" class="row" @click="pickDlna(d)">
          <Check v-if="p.castName === d.name" :size="13" class="ck" /><span v-else class="dot" />
          <span class="nm ellipsis">{{ d.name }}</span>
        </button>
      </div>

      <div v-if="ha.length" class="grp">
        <div class="hd">Home Assistant</div>
        <button v-for="d in ha" :key="d.entity_id" class="row" @click="pickHa(d)">
          <Check v-if="p.castEntity === d.entity_id" :size="13" class="ck" /><span v-else class="dot" />
          <span class="nm ellipsis">{{ d.name }}</span>
        </button>
      </div>

      <!-- 小桥被浏览器拦：给一行可点操作，不弹页面 -->
      <button v-if="blocked" class="row warn" @click="askLocalNetwork">
        <Cast :size="13" /><span>允许本地网络访问（DLNA 小桥被拦）</span>
      </button>

      <!-- 什么都发现不到时，只给一行字，不再铺一整页说明 -->
      <p v-if="!canNative && !dlna.length && !ha.length && !err && !blocked" class="tip">
        {{ busy ? "正在扫描…" : "这台浏览器发现不到投屏设备（用 Safari 打开即可直接选 AirPlay 设备）" }}
      </p>
      <p v-if="err" class="tip err">{{ err }}</p>

      <button class="row scan" @click="scan">
        <RefreshCw :size="13" :class="{ spin: busy }" /><span>重新扫描</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.wrap { position: fixed; inset: 0; z-index: 60; }
.menu { position: absolute; right: 16px; bottom: calc(var(--bar-h) + 10px); width: 268px; max-height: 60vh;
        overflow: auto; padding: 6px; border-radius: 12px; background: var(--bg-elev);
        border: 0.5px solid var(--hair); box-shadow: var(--shadow); }
.cur { display: flex; align-items: center; gap: 7px; padding: 8px 10px; color: var(--acc); font-size: 13px; }
.cur .nm { flex: 1; min-width: 0; font-weight: 600; }
.x { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 10px;
     background: var(--fill); color: var(--fg2); font-size: 11.5px; }
.row { display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; padding: 8px 10px;
       border-radius: 8px; font-size: 13px; color: var(--fg); }
.row:hover { background: var(--fill); }
.row .nm { flex: 1; min-width: 0; }
.ck { color: var(--acc); flex: none; }
.dot { width: 13px; flex: none; }
.grp { border-top: 0.5px solid var(--hair); margin-top: 4px; padding-top: 4px; }
.hd { padding: 5px 10px 2px; font-size: 11px; color: var(--fg3); letter-spacing: .04em; }
.tip { padding: 10px; font-size: 12.5px; color: var(--fg2); line-height: 1.55; }
.tip.err { color: #ff9f0a; white-space: pre-wrap; }
.warn { color: #ff9f0a; font-size: 12.5px; }
.scan { border-top: 0.5px solid var(--hair); margin-top: 4px; color: var(--fg2); font-size: 12.5px; }
.spin { animation: sp .8s linear infinite; }
@keyframes sp { to { transform: rotate(360deg) } }
</style>
