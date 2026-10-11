/**
 * R-Music 前端增强脚本 (Upgrade-safe, 零侵入)
 * 仅保留：顶部导航栏品牌 Logo；并清除旧版 Service Worker 缓存，保证增强脚本生效
 */
(function () {
  window.__RM_VERSION = "20261012m";

  (async function killOldServiceWorker() {
    try {
      let dirty = false;
      if ("serviceWorker" in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        for (const r of regs) { await r.unregister(); dirty = true; }
      }
      if (window.caches) {
        const keys = await caches.keys();
        for (const k of keys) { await caches.delete(k); dirty = true; }
      }
      if (dirty && !sessionStorage.getItem("rm-sw-cleaned")) {
        sessionStorage.setItem("rm-sw-cleaned", "1");
        location.reload();
      }
    } catch (e) { /* 忽略 */ }
  })();

  function injectBrandLogo() {
    const nav = document.querySelector("nav");
    if (!nav || document.querySelector(".r-music-brand")) return;
    const el = document.createElement("div");
    el.className = "r-music-brand";
    el.innerHTML = '<a href="/" class="r-music-logo-link" title="R智能音乐中枢">' +
      '<img src="/custom-logo.png" alt="R-Music" class="r-music-logo-img" />' +
      '<span class="r-music-brand-text">R-Music</span></a>';
    const links = nav.querySelector(".navigation-links");
    links ? nav.insertBefore(el, links) : nav.prepend(el);
  }

  function loop() { injectBrandLogo(); }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", loop) : loop();
  setInterval(loop, 1500);
})();

/* 强制 Howler 使用 HTML5 Audio 模式（解决 Web Audio CORS 解码问题） */
(function() {
  const _Howl = window.Howl;
  if (!_Howl) return;
  window.Howl = function(opts) {
    opts = opts || {};
    opts.html5 = true;
    return new _Howl(opts);
  };
  window.Howl.prototype = _Howl.prototype;
})();

/* 版本闸门：服务端构建标识变化时，自动清理旧 Service Worker 与缓存并重载一次。
   目的：避免用户长期停留在旧页面，继续用修复前拿到的失效/试听片段链接播放。 */
(function () {
  var KEY = "rm-server-build";
  try {
    fetch("/api/version?t=" + Date.now(), { cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.build) return;
        var old = localStorage.getItem(KEY);
        localStorage.setItem(KEY, d.build);
        if (!old || old === d.build) return;
        if (sessionStorage.getItem("rm-selfheal")) return;
        sessionStorage.setItem("rm-selfheal", "1");
        var reload = function () { location.reload(); };
        if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
          navigator.serviceWorker.getRegistrations().then(function (rs) {
            rs.forEach(function (r) { r.unregister(); });
            if (window.caches && caches.keys) {
              caches.keys().then(function (ks) {
                return Promise.all(ks.map(function (k) { return caches.delete(k); }));
              }).then(reload).catch(reload);
            } else { reload(); }
          }).catch(reload);
        } else { reload(); }
      })
      .catch(function () {});
  } catch (e) {}
})();
