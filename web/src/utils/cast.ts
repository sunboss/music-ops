/**
 * 本地自动发现投屏。
 *
 * 实测本网络里只有 AirPlay 设备（Apple TV HD、Mac mini），没有 DLNA 渲染器、没有 Chromecast，
 * 所以策略是「用各浏览器原生能发现的东西」：
 *   - Safari（iPhone / iPad / Mac）：调用系统 AirPlay 选择器 —— 系统自动列出局域网的 AirPlay 设备，
 *     零配置、自动发现（这是本网络唯一真正可用的通道）
 *   - Chrome / Edge：Chrome 看不到 AirPlay 设备，只能走它自己的 Remote Playback（Cast）；
 *     如实提示用户改用 Safari，而不是假装列表是空的
 *   - DLNA：浏览器无法发 SSDP 组播，必须由本机一个小桥代劳（见 /tools/dlna-bridge.py），
 *     页面自动探测 127.0.0.1:8787
 */

export type CastMode = "off" | "airplay" | "remote" | "dlna";

let el: HTMLAudioElement | null = null;

/** 投屏专用的隐藏 audio 元素：让系统把这一路音频路由到设备 */
export function castEl(): HTMLAudioElement {
  if (el) return el;
  el = document.createElement("audio");
  el.id = "rm-cast";
  el.setAttribute("x-webkit-airplay", "allow");
  el.preload = "none";
  el.style.display = "none";
  document.body.appendChild(el);
  return el;
}

const anyEl = () => castEl() as any;

/** Safari 系：有系统 AirPlay 选择器 */
export function airplaySupported(): boolean {
  return typeof anyEl().webkitShowPlaybackTargetPicker === "function";
}

/** Chromium 系：有 Remote Playback（Cast） */
export function remoteSupported(): boolean {
  return "remote" in HTMLMediaElement.prototype;
}

/** Safari 是否已经把这一路音频投到无线设备上 */
export function airplayActive(): boolean {
  return Boolean(anyEl().webkitCurrentPlaybackTargetIsWireless);
}

export function castTargetName(): string {
  const a = anyEl();
  if (a.webkitCurrentPlaybackTargetIsWireless && a.webkitCurrentPlaybackTargetName) {
    return String(a.webkitCurrentPlaybackTargetName);
  }
  return "";
}

export interface CastHooks {
  onTime?: (cur: number, dur: number) => void;
  onState?: () => void;
}

const hooks = new WeakMap<HTMLAudioElement, CastHooks>();

function bind() {
  const a = castEl();
  if (hooks.has(a)) return;
  a.addEventListener("timeupdate", () => {
    hooks.get(a)?.onTime?.(a.currentTime || 0, a.duration || 0);
  });
  a.addEventListener("play", () => hooks.get(a)?.onState?.());
  a.addEventListener("pause", () => hooks.get(a)?.onState?.());
  a.addEventListener("ended", () => hooks.get(a)?.onState?.());
  if (airplaySupported()) {
    a.addEventListener("webkitplaybacktargetavailabilitychanged", () => hooks.get(a)?.onState?.());
  }
  const r = anyEl().remote;
  if (r && r.addEventListener) {
    ["connect", "connecting", "disconnect"].forEach((ev) =>
      r.addEventListener(ev, () => hooks.get(a)?.onState?.()));
  }
  hooks.set(a, {});
}

/**
 * 把当前这首歌交给系统投屏。
 *
 * 关键：AirPlay 选择器必须在**用户手势的同步流程**里调用。
 * 之前写成先 `await play()` 再调选择器，await 一让步手势上下文就失效，
 * WebKit 会静默忽略 `webkitShowPlaybackTargetPicker()`（按钮点了没反应、也不报错）。
 * 所以这里同步先把选择器弹出来，播放放到后面异步做。
 */
export function startCast(url: string, opts: CastHooks = {}): Promise<CastMode> | CastMode {
  const a = castEl();
  bind();
  hooks.set(a, opts);
  if (a.src !== url) a.src = url;
  if (airplaySupported()) {
    anyEl().webkitShowPlaybackTargetPicker();     // 同步！系统弹窗自动列出 AirPlay 设备
    void a.play().catch(() => { /* 交给系统选择器，本地自动播放被拦无所谓 */ });
    return "airplay" as CastMode;
  }
  return startRemote(a);
}

async function startRemote(a: HTMLAudioElement): Promise<CastMode> {
  try {
    await a.play();
  } catch {
    /* 自动播放被拦也继续：下面 prompt 同样是用户手势触发的 */
  }
  if (remoteSupported() && anyEl().remote) {
    await anyEl().remote.prompt();                // Chrome 自己的设备选择器
    return "remote" as CastMode;
  }
  throw new Error("这个浏览器既没有 AirPlay 选择器也没有 Remote Playback；请用 Safari 投屏");
}

export async function stopCast() {
  const a = castEl();
  try { a.pause(); } catch { /* 忽略 */ }
  a.removeAttribute("src");
  try { a.load(); } catch { /* 忽略 */ }
}

/** 换歌时同步给设备（投屏中才需要） */
export function syncCastTrack(url: string) {
  const a = castEl();
  if (airplayActive() && url && a.src !== url) {
    a.src = url;
    void a.play().catch(() => {});
  }
}

// ---------------------------------------------------------------- DLNA 本地小桥
const BRIDGE = "http://127.0.0.1:8787";

export interface DlnaDevice { name: string; ip: string; control?: string }

export type BridgeState = "ok" | "down" | "blocked";

/** Chrome 的「本地网络访问」权限状态：公网页面访问 127.0.0.1 会被它拦住 */
export async function localNetworkPermission(): Promise<string> {
  try {
    const nav = navigator as any;
    if (!nav.permissions?.query) return "unknown";
    const st = await nav.permissions.query({ name: "local-network-access" });
    return String(st.state || "unknown");
  } catch {
    return "unknown";
  }
}

/**
 * 探测本机小桥。
 * 注意：Chrome 对「公网页面 -> 127.0.0.1」有本地网络访问限制，
 * 请求会在浏览器里就被拦掉（桥上看不到任何请求），此时状态是 blocked 而不是 down，
 * 界面要给出「去允许本地网络访问」而不是「去启动小桥」——两者原因完全不同。
 */
export async function bridgeState(): Promise<BridgeState> {
  try {
    const r = await fetch(BRIDGE + "/health", { signal: AbortSignal.timeout(2000) });
    return r.ok ? "ok" : "down";
  } catch {
    const perm = await localNetworkPermission();
    return perm === "denied" ? "blocked" : "down";
  }
}

export async function dlnaDevices(): Promise<DlnaDevice[]> {
  const r = await fetch(BRIDGE + "/devices", { signal: AbortSignal.timeout(6000) });
  if (!r.ok) throw new Error("DLNA 小桥返回 " + r.status);
  const d = await r.json();
  return (d.devices || []) as DlnaDevice[];
}

export async function dlnaCast(device: DlnaDevice, url: string): Promise<void> {
  const r = await fetch(BRIDGE + "/cast", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ control: device.control, url }),
  });
  if (!r.ok) throw new Error("DLNA 投屏失败：" + ((await r.text()) || r.status));
}

export async function dlnaStop(device: DlnaDevice) {
  try {
    await fetch(BRIDGE + "/stop", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ control: device.control }),
    });
  } catch { /* 设备可能已停 */ }
}

export const DLNA_BRIDGE_CMD = "python3 tools/dlna-bridge.py";

/** 探测不出来但确实是桥在跑时的兜底判断：再探一次是否被权限拦（避免误报"没启动"） */
export async function bridgeMaybeRunning(): Promise<boolean> {
  return (await localNetworkPermission()) === "denied";
}
