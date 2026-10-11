// R-Music: 清除旧版 Workbox 预缓存，避免浏览器一直使用过期的首页（导致增强脚本不生效）
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
    await self.clients.claim();
    if (keys.length > 0) {
      const list = await self.clients.matchAll({ type: "window" });
      list.forEach((c) => c.navigate(c.url));
    }
  })());
});
