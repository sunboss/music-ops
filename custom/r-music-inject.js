/**
 * R-Music 前端增强脚本 (Upgrade-safe, 零侵入)
 * 仅保留：顶部导航栏品牌 Logo；并清除旧版 Service Worker 缓存，保证增强脚本生效
 */
(function () {
  window.__RM_VERSION = "20261012y";

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

/* AI 音乐面板：一句话点歌 / 生成电台歌单，面板内连续播放（自动下一首、失败自动跳过） */
(function () {
  if (window.__rmAI || document.getElementById("rm-ai-btn")) return;
  window.__rmAI = true;

  var SCENES = ["深夜写代码", "开车兜风", "运动健身", "专注学习", "助眠放松", "心情不好"];
  var Q = {list: [], i: -1, busy: false};

  var css = document.createElement("style");
  css.textContent = [
    "#rm-ai-btn{position:fixed;right:18px;bottom:104px;z-index:9998;padding:10px 16px;border-radius:22px;",
    "background:linear-gradient(135deg,#00F2FE,#7F00FF);color:#fff;font:600 14px/1 -apple-system,'PingFang SC',sans-serif;",
    "cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.35);user-select:none}",
    "#rm-ai-panel{position:fixed;right:18px;bottom:150px;z-index:9999;width:min(94vw,400px);max-height:76vh;",
    "background:rgba(24,26,32,.97);color:#e8eef6;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.5);",
    "display:none;flex-direction:column;overflow:hidden;font:14px/1.6 -apple-system,'PingFang SC',sans-serif}",
    "#rm-ai-panel .hd{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;",
    "font-weight:600;background:rgba(255,255,255,.06)}",
    "#rm-ai-panel .hd span{cursor:pointer;opacity:.7;font-size:18px;line-height:1;padding:0 4px}",
    "#rm-ai-panel .bd{padding:10px 14px 6px;display:flex;gap:8px}",
    "#rm-ai-input{flex:1;min-width:0;padding:9px 12px;border-radius:9px;border:1px solid rgba(255,255,255,.18);",
    "background:rgba(255,255,255,.08);color:#fff;font-size:14px;outline:none}",
    "#rm-ai-go{padding:9px 13px;border:0;border-radius:9px;background:#4FACFE;color:#fff;font-weight:600;cursor:pointer;white-space:nowrap}",
    "#rm-ai-mic{padding:9px 11px;border:0;border-radius:9px;background:rgba(255,255,255,.12);color:#fff;cursor:pointer;white-space:nowrap;font-size:15px}",
    "#rm-ai-mic.on{background:#ff4d6d;animation:rm-pulse 1s infinite}",
    "@keyframes rm-pulse{0%,100%{opacity:1}50%{opacity:.45}}",
    "#rm-ai-go.radio{background:#7F00FF}",
    "#rm-ai-chips{padding:0 14px 6px;display:flex;flex-wrap:wrap;gap:6px}",
    "#rm-ai-chips i{padding:3px 8px;border-radius:11px;background:rgba(255,255,255,.09);font-size:12px;",
    "font-style:normal;cursor:pointer}",
    "#rm-ai-chips i:hover{background:rgba(255,255,255,.2)}",
    "#rm-ai-now{padding:7px 14px;font-size:12.5px;background:rgba(79,172,254,.16);display:none}",
    "#rm-ai-reply{padding:2px 14px 6px;font-size:13px;opacity:.9}",
    "#rm-ai-list{overflow:auto;padding:0 8px 8px;flex:1}",
    "#rm-ai-list .it{padding:8px 10px;border-radius:9px;cursor:pointer;display:flex;justify-content:space-between;gap:8px}",
    "#rm-ai-list .it:hover{background:rgba(255,255,255,.09)}",
    "#rm-ai-list .it.on{background:rgba(79,172,254,.22)}",
    "#rm-ai-list .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    "#rm-ai-list .ar{font-size:12px;opacity:.65}",
    "#rm-ai-list .du{font-size:12px;opacity:.6;flex:none}",
    "#rm-ai-ctl{display:none;align-items:center;gap:10px;padding:8px 14px 4px;border-top:1px solid rgba(255,255,255,.08)}",
    "#rm-ai-ctl b{cursor:pointer;font-size:17px;font-weight:400;padding:0 6px;user-select:none}",
    "#rm-ai-ctl b:hover{opacity:.7}",
    "#rm-ai-audio{display:none;width:calc(100% - 28px);margin:0 14px 12px}"
  ].join("");
  document.head.appendChild(css);

  var btn = document.createElement("div");
  btn.id = "rm-ai-btn"; btn.textContent = "AI 音乐";
  var panel = document.createElement("div");
  panel.id = "rm-ai-panel";
  panel.innerHTML =
    '<div class="hd"><span style="cursor:default;font-weight:600">AI 音乐<span id="rm-ai-title" ' +
    'style="font-weight:400;opacity:.7;font-size:12px;margin-left:8px"></span></span>' +
    '<span id="rm-ai-x">&times;</span></div>' +
    '<div class="bd"><input id="rm-ai-input" placeholder="说一句，或用麦克风说">' +
    '<button id="rm-ai-mic" title="按住说话（语音点歌）" style="display:none">&#127908;</button>' +
    '<button id="rm-ai-go">点歌</button></div>' +
    '<div id="rm-ai-chips"></div>' +
    '<div id="rm-ai-reply"></div><div id="rm-ai-now"></div>' +
    '<div id="rm-ai-list"></div>' +
    '<div id="rm-ai-ctl"><b id="rm-ai-prev">&#9198;</b><b id="rm-ai-play">&#9208;</b>' +
    '<b id="rm-ai-next">&#9197;</b><span id="rm-ai-pos" style="font-size:12px;opacity:.65"></span></div>' +
    '<audio id="rm-ai-audio" controls preload="none"></audio>';
  document.body.appendChild(btn);
  document.body.appendChild(panel);

  var audio = document.getElementById("rm-ai-audio");
  var nowEl = document.getElementById("rm-ai-now");
  var posEl = document.getElementById("rm-ai-pos");
  var listEl = document.getElementById("rm-ai-list");
  var repEl = document.getElementById("rm-ai-reply");

  document.getElementById("rm-ai-chips").innerHTML = SCENES.map(function (s) {
    return "<i>" + s + "</i>";
  }).join("");
  Array.prototype.forEach.call(document.querySelectorAll("#rm-ai-chips i"), function (el) {
    el.onclick = function () {
      document.getElementById("rm-ai-input").value = el.textContent;
      ask("radio");
    };
  });

  function quietOthers() {
    try {
      Array.prototype.forEach.call(document.querySelectorAll("audio"), function (x) {
        if (x !== audio) x.pause();
      });
    } catch (e) {}
  }

  function draw() {
    listEl.innerHTML = "";
    Q.list.forEach(function (s, i) {
      var it = document.createElement("div");
      it.className = "it" + (i === Q.i ? " on" : "");
      var m = Math.floor(s.duration / 60), ss = Math.round(s.duration % 60);
      it.innerHTML = '<div class="nm">' + (s.name || "") +
        '<div class="ar">' + (s.artist || "") + '</div></div>' +
        '<div class="du">' + (i === Q.i ? "▶ " : "") + m + ":" + (ss < 10 ? "0" : "") + ss + "</div>";
      if (s.playable === false) {
        it.style.opacity = ".45";
        it.title = "这首歌暂时没有完整音源";
      }
      it.onclick = function () {
        if (s.playable === false) { alert("这首歌暂时没有完整音源（各平台只有试听片段）"); return; }
        playAt(i);
      };
      listEl.appendChild(it);
    });
  }

  function markDead(i) {
    if (Q.list[i]) { Q.list[i].playable = false; }
    draw();
  }

  function playAt(i) {
    if (i < 0 || i >= Q.list.length) { nowEl.textContent = "歌单播完了"; return; }
    Q.i = i; draw();
    var s = Q.list[i];
    nowEl.style.display = "block";
    nowEl.textContent = "加载中：" + s.name + " - " + s.artist;
    document.getElementById("rm-ai-ctl").style.display = "flex";
    fetch("/api/song/url?id=" + s.id).then(function (r) { return r.json(); }).then(function (d) {
      var t = ((d.data || [])[0] || {});
      if (!t.url || t.source === "no-source") {
        markDead(i); nowEl.textContent = "这首没有完整音源，自动跳过";
        setTimeout(function () { playAt(i + 1); }, 600);
        return;
      }
      quietOthers();
      audio.src = t.url;
      audio.style.display = "block";
      audio.play().catch(function () {});
      nowEl.textContent = "正在播放：" + s.name + " - " + s.artist;
    }).catch(function () { markDead(i); setTimeout(function () { playAt(i + 1); }, 600); });
  }

  audio.addEventListener("ended", function () { playAt(Q.i + 1); });
  audio.addEventListener("error", function () {
    if (!audio.src) return;
    markDead(Q.i);
    setTimeout(function () { playAt(Q.i + 1); }, 600);
  });
  audio.addEventListener("timeupdate", function () {
    if (!audio.duration) return;
    var f = function (t) { var m = Math.floor(t / 60), s = Math.floor(t % 60);
      return m + ":" + (s < 10 ? "0" : "") + s; };
    posEl.textContent = f(audio.currentTime) + " / " + f(audio.duration) +
      (Q.list.length ? "  (" + (Q.i + 1) + "/" + Q.list.length + ")" : "");
  });

  document.getElementById("rm-ai-prev").onclick = function () { playAt(Math.max(0, Q.i - 1)); };
  document.getElementById("rm-ai-next").onclick = function () { playAt(Q.i + 1); };
  document.getElementById("rm-ai-play").onclick = function () {
    if (audio.paused) { audio.play().catch(function () {}); } else { audio.pause(); }
  };

  function ask(mode) {
    var q = (document.getElementById("rm-ai-input").value || "").trim();
    if (!q || Q.busy) return;
    Q.busy = true;
    var radio = mode === "radio";
    var goEl = document.getElementById("rm-ai-go");
    goEl.textContent = radio ? "生成中…" : "想一下…";
    repEl.textContent = radio ? "正在为你编排歌单（约需 10-30 秒）…" : "想一下…";
    listEl.innerHTML = "";
    document.getElementById("rm-ai-title").textContent = "";
    fetch(radio ? "/api/ai/radio" : "/api/ai/query",
          {method: "POST", headers: {"Content-Type": "application/json"},
           body: JSON.stringify({q: q, count: 15})})
      .then(function (r) { return r.json(); })
      .then(function (d) {
        Q.busy = false;
        goEl.textContent = radio ? "电台" : "点歌";
        if (d.error) { repEl.textContent = d.error; return; }
        if (d.title) document.getElementById("rm-ai-title").textContent = d.title;
        var n = (d.songs || []).filter(function (s) { return s.playable !== false; }).length;
        repEl.textContent = (d.reply || "") + (radio ? "　共 " + n + " 首可播" : "");
        if (d.picked) { repEl.textContent += "，" + d.picked + " 首为 AI 精选"; }
        Q.list = d.songs || []; Q.i = -1;
        draw();
        if (radio && Q.list.length) {
          var first = Q.list.findIndex(function (s) { return s.playable !== false; });
          playAt(first < 0 ? 0 : first);
        }
      })
      .catch(function (e) {
        Q.busy = false;
        goEl.textContent = radio ? "电台" : "点歌";
        repEl.textContent = "请求失败：" + e;
      });
  }

  btn.onclick = function () {
    panel.style.display = (panel.style.display === "flex") ? "none" : "flex";
    if (panel.style.display === "flex") document.getElementById("rm-ai-input").focus();
  };
  document.getElementById("rm-ai-x").onclick = function () { panel.style.display = "none"; };
  // 语音点歌：浏览器原生语音识别（HTTPS 下可用），说完直接生成电台
  (function () {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    var mic = document.getElementById("rm-ai-mic");
    if (!SR || !mic) { return; }
    mic.style.display = "block";
    var rec = null;
    mic.onclick = function () {
      if (rec) { try { rec.stop(); } catch (e) {} return; }
      rec = new SR();
      rec.lang = "zh-CN";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      mic.classList.add("on");
      var old = document.getElementById("rm-ai-reply").textContent;
      document.getElementById("rm-ai-reply").textContent = "在听你说…";
      rec.onresult = function (e) {
        var t = (e.results && e.results[0] && e.results[0][0] && e.results[0][0].transcript) || "";
        document.getElementById("rm-ai-input").value = t;
        rec = null; mic.classList.remove("on");
        if (t) { ask("radio"); } else { document.getElementById("rm-ai-reply").textContent = old; }
      };
      rec.onerror = function (e) {
        rec = null; mic.classList.remove("on");
        document.getElementById("rm-ai-reply").textContent =
          (e.error === "not-allowed") ? "麦克风未授权，请在浏览器里允许后重试" : ("语音识别失败：" + e.error);
      };
      rec.onend = function () { mic.classList.remove("on"); rec = null; };
      try { rec.start(); } catch (e) {
        mic.classList.remove("on"); rec = null;
        document.getElementById("rm-ai-reply").textContent = "语音识别启动失败：" + e;
      }
    };
  })();

  document.getElementById("rm-ai-go").onclick = function () { ask("song"); };
  document.getElementById("rm-ai-go").ondblclick = function () { ask("radio"); };
  document.getElementById("rm-ai-input").addEventListener("keydown", function (e) {
    if (e.key === "Enter") { ask(e.shiftKey ? "radio" : "song"); }
  });
})();


/* 口味记忆：记录真实收听行为（听了 / 跳过），服务端据此让 AI 更懂你 */
(function () {
  if (window.__rmTaste) return;
  window.__rmTaste = true;

  function sidOf(u) {
    var m = /[?&]id=(\d+)/.exec(u || "");
    return m ? m[1] : null;
  }
  function send(id, action, played, dur) {
    try {
      fetch("/api/client-report", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({kind: "taste", id: id, action: action,
                              played: Math.round(played || 0), dur: Math.round(dur || 0),
                              v: window.__RM_VERSION})
      });
    } catch (e) {}
  }

  var cur = null, timer = null;

  function flush(reason) {
    if (!cur || !cur.sid) { cur = null; return; }
    var played = cur.max || 0, dur = cur.dur || 0;
    if (!cur.reported) {                       // 已上报过就不再重复
      if (reason === "ended" || played >= 30) { send(cur.sid, "play", played, dur); }
      else if (played >= 3 && played < 20) { send(cur.sid, "skip", played, dur); }  // 听了十几秒就切走 = 不喜欢
    }
    cur = null;
  }

  function tick() {
    var best = 0, el = null;
    Array.prototype.forEach.call(document.querySelectorAll("audio"), function (a) {
      if (!a.paused && a.currentTime > best) { best = a.currentTime; el = a; }
    });
    if (!el) { return; }
    var sid = sidOf(el.src);
    if (!sid) { return; }
    if (!cur || cur.sid !== sid) { flush("switch"); cur = {sid: sid, max: 0, dur: 0}; }
    cur.max = Math.max(cur.max || 0, el.currentTime || 0);
    cur.dur = el.duration || cur.dur || 0;
    // 听满 30 秒就立刻记账：不能只等切歌/关闭页面上报，
    // 否则用户一直听下去这条记录永远不会落库
    if (cur.max >= 30 && !cur.reported) {
      cur.reported = true;
      send(cur.sid, "play", cur.max, cur.dur);
    }
    if (el.ended) { flush("ended"); }
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { flush("hide"); } else { start(); }
  });
  function start() { if (!timer) { timer = setInterval(tick, 3000); } }
  start();
})();
