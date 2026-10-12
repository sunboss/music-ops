/**
 * 投屏：通过你家里的 Home Assistant 把歌推给 AirPlay / DLNA / Chromecast 设备。
 *
 * 为什么必须经 HA：设备在你家局域网（192.168.1.x），而 R-Music 服务器在东京，
 * 网络不通；HA 在局域网上，Music Assistant 又正好支持这些协议。
 * 地址与长期令牌只存在你自己的浏览器 localStorage 里，不会发到我们服务器。
 */

export interface HaPlayer {
  entity_id: string;
  name: string;
  state: string;
}

const KEY_URL = "rm-ha-url";
const KEY_TOKEN = "rm-ha-token";

export function haCfg() {
  return {
    url: (localStorage.getItem(KEY_URL) || "").replace(/\/+$/, ""),
    token: localStorage.getItem(KEY_TOKEN) || "",
  };
}

export function haSave(url: string, token: string) {
  localStorage.setItem(KEY_URL, url.trim().replace(/\/+$/, ""));
  localStorage.setItem(KEY_TOKEN, token.trim());
}

export function haReady() {
  const c = haCfg();
  return Boolean(c.url && c.token);
}

/** 把 fetch 的失败翻译成他能照着做的提示 */
export function haHint(e: unknown): string {
  const m = e instanceof Error ? e.message : String(e);
  if (m.includes("Failed to fetch") || m.includes("NetworkError") || m.includes("Load failed")) {
    return "连不上 Home Assistant：可能地址不对、不在同一网络，或被浏览器 CORS 拦住。"
      + "若确认地址能打开，就在 HA 的 configuration.yaml 里加：\n"
      + "http:\n  cors_allowed_origins:\n    - https://music.1234r.com";
  }
  return m;
}

async function haFetch(path: string, init?: RequestInit): Promise<any> {
  const c = haCfg();
  if (!c.url || !c.token) throw new Error("还没配置 Home Assistant（设置 → 投屏）");
  const r = await fetch(c.url + path, {
    ...init,
    headers: {
      Authorization: "Bearer " + c.token,
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string>) || {}),
    },
  });
  if (!r.ok) {
    throw new Error(r.status === 401 ? "令牌被拒绝（401）：长期访问令牌不对或已失效"
      : r.status === 404 ? "地址不对（404）：检查 HA 地址是否带上端口 8123"
      : "Home Assistant 返回 " + r.status);
  }
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

/** 列出 HA 里所有播放器（含 Music Assistant 暴露的 AirPlay / DLNA 设备） */
export async function haPlayers(): Promise<HaPlayer[]> {
  const st = (await haFetch("/api/states")) as any[];
  return (st || [])
    .filter((s) => String(s.entity_id || "").startsWith("media_player."))
    .map((s) => ({
      entity_id: s.entity_id,
      name: (s.attributes && s.attributes.friendly_name) || s.entity_id,
      state: String(s.state || ""),
    }))
    .sort((a, b) => (a.state === "unavailable" ? 1 : 0) - (b.state === "unavailable" ? 1 : 0)
      || a.name.localeCompare(b.name, "zh"));
}

/** 把当前这首歌推给指定播放器（音频直链是公网的，任何渲染器都能取） */
export async function haCast(entityId: string, streamUrl: string, title: string) {
  return haFetch("/api/services/media_player/play_media", {
    method: "POST",
    body: JSON.stringify({
      entity_id: entityId,
      media_content_id: streamUrl,
      media_content_type: "music",
      extra: title ? { title } : undefined,
    }),
  });
}

export async function haStop(entityId: string) {
  return haFetch("/api/services/media_player/media_stop", {
    method: "POST",
    body: JSON.stringify({ entity_id: entityId }),
  });
}
