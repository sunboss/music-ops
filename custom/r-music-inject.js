/**
 * R-Music 前端增强脚本 (Upgrade-safe, 零侵入)
 * 仅保留：顶部导航栏品牌 Logo；并清除旧版 Service Worker 缓存，保证增强脚本生效
 */
(function () {
  window.__RM_VERSION = "20261012t";

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

/* 客户端回报：让服务端能看到「这台设备到底在播什么」——排查用户端异常时最关键的信息 */
(function () {
  function report(obj) {
    try {
      obj.v = window.__RM_VERSION;
      obj.ua = navigator.userAgent;
      var body = JSON.stringify(obj);
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/client-report", new Blob([body], {type: "application/json"}));
      } else {
        fetch("/api/client-report", {method: "POST", body: body, keepalive: true}).catch(function () {});
      }
    } catch (e) {}
  }
  // 页面状态（含当前注册的 Service Worker，便于判断是否是旧版缓存）
  setTimeout(function () {
    var info = {kind: "page", url: location.href, sw: "", ctrl: "", caches: ""};
    var finish = function () { report(info); };
    var jobs = [];
    if (navigator.serviceWorker) {
      info.ctrl = navigator.serviceWorker.controller
        ? navigator.serviceWorker.controller.scriptURL : "(无控制器)";
      if (navigator.serviceWorker.getRegistrations) {
        jobs.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
          info.sw = rs.map(function (r) {
            return [r.active && r.active.scriptURL, r.installing && "installing",
                    r.waiting && "waiting"].filter(Boolean).join(",") || "?";
          }).join(" | ") || "(无注册)";
        }).catch(function () {}));
      }
    }
    if (window.caches && caches.keys) {
      jobs.push(caches.keys().then(function (ks) {
        info.caches = ks.join(",") || "(空)";
      }).catch(function () {}));
    }
    Promise.all(jobs).then(finish).catch(finish);
  }, 2500);

  // 每次开始播放，回报实际地址与浏览器识别到的时长。
  // 注意：播放器的音频对象是 Howler 用 new Audio() 创建的，不挂在 DOM 上，
  // 因此 document 上的 play 事件收不到 —— 必须挂钩 HTMLMediaElement.prototype.play。
  (function () {
    var op = HTMLMediaElement.prototype.play;
    if (!op) return;
    HTMLMediaElement.prototype.play = function () {
      var a = this;
      // 拦截网易云「外链兜底」：前端在取不到源时会播
      // https://music.163.com/song/media/outer/url?id=xxx，它对 VIP 曲只给 30 秒试听。
      // 改走我们自己的代理——由服务端解析完整音源并校验真实时长（拿不到就如实报无音源）。
      try {
        var cur = a.currentSrc || a.src || "";
        var m = cur.match(/music\.163\.com\/song\/media\/outer\/url\?id=(\d+)/);
        if (m) {
          var fixed = "/api/audio/proxy?id=" + m[1];
          a.src = fixed;
          try { a.load(); } catch (e2) {}
          report({kind: "rewrite", from: cur.slice(0, 90), to: fixed});
        }
      } catch (e3) {}
      var fire = function () {
        report({kind: "play", src: a.currentSrc || a.src || "", dur: a.duration || 0,
                t: a.currentTime || 0});
      };
      if (a.duration) { setTimeout(fire, 800); }
      else { a.addEventListener("loadedmetadata", function () { setTimeout(fire, 800); },
                                {once: true}); }
      return op.apply(this, arguments);
    };
  })();
})();

/* 取源监控：把播放器每次请求 /song/url 拿到的内容回报给服务端。
   关键用途：判断取源请求是否被 Service Worker 的旧缓存截住
   （如果 App 收到了响应、而服务端访问日志里没有这条请求，就是缓存命中）。 */
(function () {
  function send(obj) {
    try {
      obj.v = window.__RM_VERSION;
      obj.ua = navigator.userAgent;
      var body = JSON.stringify(obj);
      if (navigator.sendBeacon) {
        navigator.sendBeacon("/api/client-report", new Blob([body], {type: "application/json"}));
      } else {
        fetch("/api/client-report", {method: "POST", body: body, keepalive: true}).catch(function () {});
      }
    } catch (e) {}
  }
  window.__rmReport = send;

  function summarize(data) {
    try {
      var d = (typeof data === "string") ? JSON.parse(data) : data;
      var it = ((d && d.data) || [])[0] || {};
      return "url=" + ((it.url || "null") + "").slice(0, 90) +
             " size=" + (it.size || 0) + " br=" + (it.br || 0) +
             " src=" + (it.source || d.source || "-") +
             " trial=" + (it.freeTrialInfo ? "yes" : "no");
    } catch (e) { return "解析失败"; }
  }

  // ---- fetch ----
  var of = window.fetch;
  if (of) {
    window.fetch = function (input, init) {
      var url = (input && input.url) || input || "";
      var p = of.apply(this, arguments);
      if (String(url).indexOf("/song/url") >= 0) {
        p.then(function (r) {
          r.clone().text().then(function (t) {
            send({kind: "songurl", via: "fetch", req: String(url).slice(0, 100), res: summarize(t)});
          }).catch(function () {});
        }).catch(function () {});
      }
      return p;
    };
  }

  // ---- XMLHttpRequest（axios 默认走这条） ----
  var OX = window.XMLHttpRequest;
  if (OX) {
    var oOpen = OX.prototype.open, oSend = OX.prototype.send;
    OX.prototype.open = function (m, u) { this.__rmUrl = u; return oOpen.apply(this, arguments); };
    OX.prototype.send = function () {
      var xhr = this;
      if (String(xhr.__rmUrl || "").indexOf("/song/url") >= 0) {
        xhr.addEventListener("load", function () {
          var cached = xhr.getResponseHeader && xhr.getResponseHeader("age");
          send({kind: "songurl", via: "xhr", req: String(xhr.__rmUrl).slice(0, 100),
                status: xhr.status, res: summarize(xhr.responseText), age: cached || ""});
        });
      }
      return oSend.apply(this, arguments);
    };
  }
})();

/* AI 点歌浮窗：直接用一句话点歌（服务端 /api/ai/query 调用大模型解析需求） */
(function () {
  if (window.__rmAI || document.getElementById("rm-ai-btn")) return;
  window.__rmAI = true;

  var css = document.createElement("style");
  css.textContent = [
    "#rm-ai-btn{position:fixed;right:18px;bottom:104px;z-index:9998;padding:10px 16px;border-radius:22px;",
    "background:linear-gradient(135deg,#00F2FE,#7F00FF);color:#fff;font:600 14px/1 -apple-system,'PingFang SC',sans-serif;",
    "cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.35);user-select:none}",
    "#rm-ai-panel{position:fixed;right:18px;bottom:150px;z-index:9999;width:min(92vw,380px);max-height:70vh;",
    "background:rgba(24,26,32,.97);color:#e8eef6;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
    "display:none;flex-direction:column;overflow:hidden;font:14px/1.6 -apple-system,'PingFang SC',sans-serif}",
    "#rm-ai-panel .hd{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;",
    "font-weight:600;background:rgba(255,255,255,.06)}",
    "#rm-ai-panel .hd span{cursor:pointer;opacity:.7;font-size:18px;line-height:1;padding:0 4px}",
    "#rm-ai-panel .bd{padding:12px 14px;display:flex;gap:8px}",
    "#rm-ai-input{flex:1;min-width:0;padding:9px 12px;border-radius:9px;border:1px solid rgba(255,255,255,.18);",
    "background:rgba(255,255,255,.08);color:#fff;font-size:14px;outline:none}",
    "#rm-ai-go{padding:9px 14px;border:0;border-radius:9px;background:#4FACFE;color:#fff;font-weight:600;cursor:pointer;white-space:nowrap}",
    "#rm-ai-reply{padding:0 14px 8px;font-size:13px;opacity:.9}",
    "#rm-ai-list{overflow:auto;padding:0 8px 10px}",
    "#rm-ai-list .it{padding:8px 10px;border-radius:9px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}",
    "#rm-ai-list .it:hover{background:rgba(255,255,255,.09)}",
    "#rm-ai-list .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    "#rm-ai-list .ar{font-size:12px;opacity:.65}",
    "#rm-ai-list .du{font-size:12px;opacity:.6;flex:none}",
    "#rm-ai-audio{display:none;width:calc(100% - 28px);margin:0 14px 12px}"
  ].join("");
  document.head.appendChild(css);

  var btn = document.createElement("div");
  btn.id = "rm-ai-btn"; btn.textContent = "AI 点歌";
  var panel = document.createElement("div");
  panel.id = "rm-ai-panel";
  panel.innerHTML =
    '<div class="hd">AI 点歌<span id="rm-ai-x">&times;</span></div>' +
    '<div class="bd"><input id="rm-ai-input" placeholder="说一句，例如：适合深夜写代码的">' +
    '<button id="rm-ai-go">点歌</button></div>' +
    '<div id="rm-ai-reply"></div><div id="rm-ai-list"></div>' +
    '<audio id="rm-ai-audio" controls preload="none"></audio>';
  document.body.appendChild(btn);
  document.body.appendChild(panel);

  function playInPanel(id, el) {
    var a = document.getElementById("rm-ai-audio");
    // 暂停站点自带播放器，避免两个声音同时响
    try {
      Array.prototype.forEach.call(document.querySelectorAll("audio"), function (x) {
        if (x !== a) { x.pause(); }
      });
    } catch (e) {}
    document.getElementById("rm-ai-reply").textContent = "取源中…";
    fetch("/api/song/url?id=" + id).then(function (r) { return r.json(); }).then(function (d) {
      var it = ((d.data || [])[0] || {});
      if (!it.url || it.source === "no-source") {
        document.getElementById("rm-ai-reply").textContent = "这首歌暂时没有完整音源";
        setTimeout(function () { if (el) el.style.opacity = "0.45"; }, 0);
        return;
      }
      a.src = it.url; a.style.display = "block"; a.play().catch(function () {});
      document.getElementById("rm-ai-reply").textContent = "正在播放" +
        (it.size ? "（完整音频 " + (it.size / 1024 / 1024).toFixed(1) + " MB）" : "");
    });
  }

  function render(d) {
    document.getElementById("rm-ai-reply").textContent = d.reply || "";
    var box = document.getElementById("rm-ai-list");
    box.innerHTML = "";
    var items = [];
    (d.songs || []).forEach(function (s) {
      var it = document.createElement("div");
      it.className = "it";
      var m = Math.floor(s.duration / 60), ss = Math.round(s.duration % 60);
      it.innerHTML = '<div class="nm">' + (s.name || "") +
        '<div class="ar">' + (s.artist || "") + '</div></div>' +
        '<div class="du">' + m + ":" + (ss < 10 ? "0" : "") + ss + "</div>";
      it.onclick = function () { playInPanel(s.id, it); };
      box.appendChild(it);
      items.push({el: it, id: s.id});
    });
    if (!items.length) { box.innerHTML = '<div class="it">没找到合适的歌，换个说法试试</div>'; return; }

    // 异步标注可用性：拿不到完整音源的置灰，避免点了没反应
    items.forEach(function (x) {
      fetch("/api/song/url?id=" + x.id).then(function (r) { return r.json(); }).then(function (res) {
        var it = ((res.data || [])[0] || {});
        if (!it.url || it.source === "no-source") {
          x.el.style.opacity = "0.45";
          x.el.onclick = function () { alert("这首歌暂时没有可用音源（各平台只有试听片段）"); };
          var badge = document.createElement("div");
          badge.className = "du"; badge.textContent = "无音源";
          x.el.appendChild(badge);
        }
      }).catch(function () {});
    });
  }

  function ask() {
    var q = (document.getElementById("rm-ai-input").value || "").trim();
    if (!q) return;
    var rep = document.getElementById("rm-ai-reply"), box = document.getElementById("rm-ai-list");
    rep.textContent = "想一下…"; box.innerHTML = "";
    fetch("/api/ai/query", {method: "POST", headers: {"Content-Type": "application/json"},
                            body: JSON.stringify({q: q})})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) { rep.textContent = d.error; return; }
        render(d);
      })
      .catch(function (e) { rep.textContent = "请求失败：" + e; });
  }

  btn.onclick = function () {
    panel.style.display = (panel.style.display === "flex") ? "none" : "flex";
    if (panel.style.display === "flex") document.getElementById("rm-ai-input").focus();
  };
  document.getElementById("rm-ai-x").onclick = function () { panel.style.display = "none"; };
  document.getElementById("rm-ai-audio").addEventListener("error", function () {
    document.getElementById("rm-ai-reply").textContent = "这首歌暂时无法播放（可能没有完整音源）";
  });
  document.getElementById("rm-ai-go").onclick = ask;
  document.getElementById("rm-ai-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter") ask();
  });
})();
