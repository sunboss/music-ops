<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Cast, X, RefreshCw, AlertTriangle, Square, Volume2, Wifi } from "lucide-vue-next";
import {
  airplaySupported, remoteSupported, airplayActive, castTargetName, startCast, stopCast,
  bridgeState, dlnaDevices, dlnaCast, DLNA_BRIDGE_CMD, localNetworkPermission,
  type DlnaDevice, type BridgeState,
} from "@/utils/cast";
import { haReady, haPlayers, haCast, haStop, haHint, type HaPlayer } from "@/utils/ha";
import { usePlayerStore } from "@/stores/player";

const p = usePlayerStore();
const err = ref("");
const busy = ref("");
const bridge = ref<BridgeState | null>(null);
const dlna = ref<DlnaDevice[]>([]);
const haList = ref<HaPlayer[]>([]);
const showHa = ref(false);

// 这台设备有什么能力，就只展示什么——不做跨设备代理
const canAirplay = airplaySupported();          // Safari 系：系统 AirPlay 选择器
const canRemote = remoteSupported();            // Chromium 系：Remote Playback（Cast）
const onChrome = !canAirplay && /Chrome|Chromium|Edg/.test(navigator.userAgent);

const streamUrl = computed(() =>
  p.current?.id ? `${location.origin}/api/ma/play?id=${p.current.id}` : "");
const airplayOn = ref(airplayActive());
const airplayName = ref(castTargetName());

function refreshAirplay() {
  airplayOn.value = airplayActive();
  airplayName.value = castTargetName();
  // 让播放条也显示出"投到哪台设备"（AirPlay 生效后 webkitCurrentPlaybackTargetName 才有值）
  if (airplayOn.value) {
    p.castName = airplayName.value || "AirPlay 设备";
    p.castMode = "airplay";
  } else if (p.castMode === "airplay") {
    p.castName = "";
    p.castMode = "off";
  }
}

async function doAirplay() {
  if (!p.current) { err.value = "先播一首歌再投屏"; return; }
  err.value = ""; busy.value = "airplay";
  try {
    // 交给这台设备的系统选择器自动发现并路由；本地播放暂停，避免两边同时出声
    if (p.playing) p.toggle();
    await startCast(streamUrl.value, {
      onState: refreshAirplay,
      onTime: (cur, dur) => { p.progress = cur || 0; if (dur) p.duration = dur; },
    });
    window.setTimeout(refreshAirplay, 800);
  } catch (e) {
    err.value = e instanceof Error ? e.message : String(e);
  } finally { busy.value = ""; }
}

async function doRemote() {
  if (!p.current) { err.value = "先播一首歌再投屏"; return; }
  err.value = ""; busy.value = "remote";
  try {
    if (p.playing) p.toggle();
    await startCast(streamUrl.value, { onState: refreshAirplay });
  } catch (e) {
    const m = e instanceof Error ? e.message : String(e);
    err.value = /Abort|NotFound/i.test(m)
      ? "这台设备没发现可投的 Chromecast（浏览器只认 Cast；AirPlay 音箱/Apple TV 要用 Safari 打开本站才能发现）"
      : m;
  } finally { busy.value = ""; }
}

async function endCast() {
  await stopCast();
  refreshAirplay();
  p.castName = "";
  p.castMode = "off";
}

async function probeBridge() {
  bridge.value = await bridgeState();
  if (bridge.value !== "ok") { dlna.value = []; return; }
  try { dlna.value = await dlnaDevices(); } catch (e) { err.value = String(e); }
}

/** 让浏览器弹出「本地网络访问」询问（这一下必须是用户点击触发的） */
async function askLocalNetwork() {
  err.value = "";
  try {
    await fetch("http://127.0.0.1:8787/health", { mode: "cors", cache: "no-store" });
  } catch { /* 被拦也正常，下面重新探一次看权限状态 */ }
  const perm = await localNetworkPermission();
  await probeBridge();
  if (bridge.value !== "ok") {
    err.value = perm === "denied"
      ? "浏览器仍然拒绝访问本地网络。请在地址栏左侧的「站点设置」里把「本地网络访问」改成允许，然后重试。"
      : "";
  }
}

async function castDlna(d: DlnaDevice) {
  if (!p.current) { err.value = "先播一首歌再投屏"; return; }
  busy.value = d.control || d.name;
  try {
    await dlnaCast(d, streamUrl.value);
    p.castName = d.name; p.castMode = "dlna";
  } catch (e) { err.value = e instanceof Error ? e.message : String(e); }
  finally { busy.value = ""; }
}

async function loadHa() {
  try { haList.value = await haPlayers(); } catch (e) { err.value = haHint(e); }
}
async function castHa(d: HaPlayer) {
  if (!p.current) { err.value = "先播一首歌再投屏"; return; }
  try {
    await haCast(d.entity_id, streamUrl.value, p.current.name);
    p.castName = d.name; p.castMode = "ha"; p.castEntity = d.entity_id;
  } catch (e) { err.value = haHint(e); }
}
async function stopHa() {
  if (p.castEntity) { try { await haStop(p.castEntity); } catch { /* 忽略 */ } }
  p.castEntity = ""; p.castName = ""; p.castMode = "off";
}

onMounted(() => { void probeBridge(); });
</script>

<template>
  <div class="mask" @click.self="p.showCast = false">
    <div class="sheet">
      <header>
        <Cast :size="17" />
        <h2>投屏</h2>
        <span class="sp" />
        <span class="who">用这台设备自己的发现</span>
        <button class="ib" title="关闭" @click="p.showCast = false"><X :size="16" /></button>
      </header>

      <div v-if="p.castName" class="now">
        <Wifi :size="15" />
        <div><b>正在投屏到 {{ p.castName }}</b><span v-if="p.current">《{{ p.current.name }}》</span></div>
        <button class="ghost" @click="p.castMode === 'ha' ? stopHa() : endCast()">
          <Square :size="12" />停止
        </button>
      </div>

      <!-- Safari / iOS / macOS：系统原生 AirPlay 发现 -->
      <section v-if="canAirplay" class="card">
        <div class="ct"><Volume2 :size="16" /><b>AirPlay</b><i class="rec">推荐</i></div>
        <p>点下面的按钮会弹出<b>系统列表</b>，由这台设备自动发现局域网里的 AirPlay 音箱与 Apple TV。</p>
        <button class="go" :disabled="!!busy" @click="doAirplay">
          {{ busy === "airplay" ? "正在唤起…" : airplayOn ? "换一台设备" : "选择设备" }}
        </button>
        <p v-if="airplayOn" class="on">已连接{{ airplayName ? "：" + airplayName : "" }}</p>
      </section>

      <!-- Chrome 等：只认 Cast；AirPlay 设备它发现不了，如实说明 -->
      <section v-else class="card">
        <div class="ct"><Volume2 :size="16" /><b>{{ onChrome ? "浏览器原生投屏（Cast）" : "浏览器投屏" }}</b></div>
        <p v-if="onChrome">
          这台设备上的 Chrome <b>发现不了 AirPlay 设备</b>（只有 Safari 调得到系统的 AirPlay 发现）。
          想投家里那台 Apple TV / HomePod，请用 <b>Safari</b> 打开本站；Chrome 只能投 Chromecast。
        </p>
        <p v-else>这台设备上的浏览器没有系统投屏选择器，换一个支持 AirPlay 的浏览器（如 Safari）即可。</p>
        <button v-if="canRemote" class="go" :disabled="!!busy" @click="doRemote">
          {{ busy === "remote" ? "正在唤起…" : "尝试浏览器发现" }}
        </button>
      </section>

      <!-- DLNA：浏览器不能自己发 SSDP，必须在「这台设备」上跑小桥 -->
      <section class="card">
        <div class="ct"><Cast :size="16" /><b>DLNA</b><i class="tag">需本机小桥</i></div>
        <template v-if="bridge === null"><p>正在探测本机小桥…</p></template>

        <!-- 桥没启动：给出启动命令 -->
        <template v-else-if="bridge === 'down'">
          <p>浏览器不能自己发 SSDP 组播，DLNA 需要在<b>这台设备</b>上跑一个小桥（其它机器上的不算）。</p>
          <code>{{ DLNA_BRIDGE_CMD }}</code>
          <button class="ghost mt" @click="probeBridge"><RefreshCw :size="13" />我已启动，重试</button>
        </template>

        <!-- 桥在跑但被浏览器拦：原因不同，引导也不同 -->
        <template v-else-if="bridge === 'blocked'">
          <p><b>浏览器拦住了对本机小桥的访问</b>（Chrome 的「本地网络访问」限制：公网页面访问 127.0.0.1 要你授权）。</p>
          <p class="dim">小桥本身可能已经在跑，只是这个页面还没被允许访问它。</p>
          <button class="go" @click="askLocalNetwork">请求本地网络访问权限</button>
          <p class="dim">没弹窗或仍失败：地址栏左侧「站点设置」→「本地网络访问」改为允许；或用 Safari 直接投 AirPlay。</p>
        </template>
        <template v-else>
          <p v-if="!dlna.length" class="dim">小桥在运行，但本网络里没有 DLNA 渲染器（实测只有 AirPlay 设备）。</p>
          <div v-else class="list">
            <button v-for="d in dlna" :key="d.control || d.name" class="dev" @click="castDlna(d)">
              <Cast :size="15" /><div><b>{{ d.name }}</b><span>{{ d.ip }}</span></div>
            </button>
          </div>
          <button class="ghost mt" @click="probeBridge"><RefreshCw :size="13" />重新扫描</button>
        </template>
      </section>

      <!-- 可选：经 Home Assistant（家里有 MA 时更灵活） -->
      <section v-if="haReady()" class="card">
        <div class="ct" @click="showHa = !showHa; showHa && loadHa()">
          <Wifi :size="16" /><b>经 Home Assistant</b><i class="tag">可选</i>
          <span class="sp" /><span class="dim">{{ showHa ? "收起" : "展开" }}</span>
        </div>
        <div v-if="showHa" class="list">
          <button v-for="d in haList" :key="d.entity_id" class="dev" @click="castHa(d)">
            <Wifi :size="15" /><div><b>{{ d.name }}</b><span>{{ d.state }}</span></div>
          </button>
          <p v-if="!haList.length" class="dim">HA 里还没有播放器（需要 Music Assistant 或 DLNA 集成）。</p>
        </div>
      </section>

      <p v-if="err" class="err"><AlertTriangle :size="14" />{{ err }}</p>
    </div>
  </div>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.4); display: flex; align-items: flex-end;
        justify-content: center; z-index: 60; }
.sheet { width: 100%; max-width: 520px; background: var(--bg-elev); border-radius: 16px 16px 0 0;
         padding: 14px 16px 22px; max-height: 80vh; overflow: auto; box-shadow: var(--shadow); }
header { display: flex; align-items: center; gap: 9px; padding-bottom: 10px; border-bottom: 0.5px solid var(--hair); }
header h2 { font-size: 16px; font-weight: 600; }
header .sp, .ct .sp { flex: 1; }
.who { font-size: 11.5px; color: var(--fg3); }
.ib { width: 30px; height: 30px; display: grid; place-items: center; color: var(--fg2); border-radius: 8px; }
.ib:hover { background: var(--fill); }
.now { display: flex; align-items: center; gap: 10px; padding: 12px 0; color: var(--acc); }
.now div { flex: 1; min-width: 0; }
.now b { display: block; font-size: 13.5px; }
.now span { font-size: 12px; color: var(--fg2); }
.ghost { display: inline-flex; align-items: center; gap: 5px; padding: 6px 12px; border-radius: 14px;
         background: var(--fill); color: var(--fg); font-size: 12.5px; }
.card { padding: 14px 0 6px; border-top: 0.5px solid var(--hair); margin-top: 6px; }
.ct { display: flex; align-items: center; gap: 8px; margin-bottom: 7px; }
.ct b { font-size: 14px; font-weight: 600; }
.rec { font-size: 10.5px; color: #fff; background: var(--acc); border-radius: 8px; padding: 1px 7px; font-style: normal; }
.tag { font-size: 10.5px; color: var(--fg3); background: var(--fill); border-radius: 8px; padding: 1px 7px; font-style: normal; }
.card p { font-size: 12.5px; color: var(--fg2); line-height: 1.6; }
.card code { display: block; margin-top: 9px; padding: 8px 10px; border-radius: 8px; background: var(--fill);
             font-size: 12px; color: var(--fg); overflow-x: auto; }
.go { margin-top: 11px; padding: 9px 20px; border-radius: 20px; background: var(--acc); color: #fff;
      font-weight: 600; font-size: 13.5px; }
.go:disabled { opacity: .6; }
.on { margin-top: 8px; color: var(--acc) !important; }
.mt { margin-top: 10px; }
.dim { color: var(--fg3); }
.list { padding-top: 4px; }
.dev { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; padding: 11px 10px; border-radius: 10px; }
.dev:hover { background: var(--fill); }
.dev div { flex: 1; min-width: 0; }
.dev b { display: block; font-size: 14px; font-weight: 500; }
.dev span { font-size: 12px; color: var(--fg2); }
.err { display: flex; gap: 7px; align-items: flex-start; white-space: pre-wrap; padding: 14px 0 0;
       color: #ff9f0a; font-size: 12.5px; line-height: 1.55; }
</style>
