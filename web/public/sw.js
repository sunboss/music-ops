/* R-Music Service Worker
 * 策略：
 *  - 应用外壳（/）：network-first，离线时回退缓存 —— 保证打开就有界面
 *  - 带 hash 的静态资源（/assets/）：cache-first（文件名变了缓存自然失效）
 *  - manifest/图标：cache-first
 *  - 音频/接口（/api/）：永不缓存 —— 音源直链有时效，接口要实时
 * 版本号手动递增（部署脚本会替换 __SWV__）。
 */
const VER = "__SWV__";
const SHELL_CACHE = `rm-shell-${VER}`;
const ASSET_CACHE = `rm-assets-${VER}`;

self.addEventListener("install", (e) => {
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) {
      if (k.startsWith("rm-") && k !== SHELL_CACHE && k !== ASSET_CACHE) {
        await caches.delete(k);
      }
    }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  const path = url.pathname;

  // 音频流与接口：绝不缓存（直链有时效、收藏/口味要实时）
  if (path.startsWith("/api/") || path.startsWith("/stream")) return;

  // 带 hash 的静态资源：cache-first
  if (path.startsWith("/assets/") || path === "/manifest.json" ||
      /^\/(favicon|apple-touch-icon|icon-\d+)\./.test(path)) {
    e.respondWith((async () => {
      const c = await caches.open(ASSET_CACHE);
      const hit = await c.match(e.request);
      if (hit) return hit;
      const r = await fetch(e.request);
      if (r.ok) c.put(e.request, r.clone());
      return r;
    })());
    return;
  }

  // SPA 外壳：network-first，离线回退
  e.respondWith((async () => {
    const c = await caches.open(SHELL_CACHE);
    try {
      const r = await fetch(e.request);
      if (r.ok && (path === "/" || path.endsWith(".html"))) c.put("/", r.clone());
      return r;
    } catch {
      const hit = await c.match("/") || await c.match(e.request);
      if (hit) return hit;
      return new Response("离线且无缓存", { status: 503, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }
  })());
});
