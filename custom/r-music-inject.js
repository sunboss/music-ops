/**
 * R-Music 专属前端增强脚本 (Upgrade-safe Zero-intrusion)
 * 1. 注入 R-Music 专属极简矢量 Logo 与品牌标头
 * 2. 注入 AirPlay & DLNA 智能投屏功能与全功能控制面板
 * 3. 增强移动端/手机端交互适配
 */

(function () {
  console.log("[R-Music] Initializing R-Music Enhancer (AirPlay / DLNA / Mobile Support)...");

  // 1. 动态注入顶部导航栏 R-Music Logo
  function injectBrandLogo() {
    const nav = document.querySelector("nav");
    if (!nav || document.querySelector(".r-music-brand")) return;

    const brandEl = document.createElement("div");
    brandEl.className = "r-music-brand";
    brandEl.innerHTML = `
      <a href="/" class="r-music-logo-link" title="R智能音乐中枢">
        <img src="/custom-logo.svg" alt="R-Music" class="r-music-logo-img" />
        <span class="r-music-brand-text">R-Music</span>
      </a>
    `;

    // 优先插入在导航链接前面
    const navLinks = nav.querySelector(".navigation-links");
    if (navLinks) {
      nav.insertBefore(brandEl, navLinks);
    } else {
      nav.prepend(brandEl);
    }
    console.log("[R-Music] Brand Logo injected successfully.");
  }

  // 2. 注入播放器 AirPlay & DLNA 投屏功能
  let castModal = null;

  function createCastModal(audio) {
    if (castModal) return castModal;

    castModal = document.createElement("div");
    castModal.className = "r-music-cast-modal";
    castModal.style.display = "none";
    castModal.innerHTML = `
      <div class="r-music-cast-overlay"></div>
      <div class="r-music-cast-content">
        <div class="r-music-cast-header">
          <div class="r-music-cast-title">
            <svg class="cast-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.92-11-11-11zm20-7H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
            </svg>
            <span>音频投屏中枢 (AirPlay & DLNA)</span>
          </div>
          <button class="r-music-cast-close" title="关闭">&times;</button>
        </div>

        <div class="r-music-cast-body">
          <div class="cast-track-info">
            <div class="cast-track-name" id="rm-cast-track-name">正在加载曲目...</div>
            <div class="cast-track-status" id="rm-cast-track-status">准备就绪，支持局域网智能电视、音响与苹果设备</div>
          </div>

          <div class="cast-action-grid">
            <button class="cast-action-btn primary" id="rm-btn-airplay">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                <path d="M6 22h12l-6-6zM21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4v-2H3V5h18v12h-4v2h4c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
              </svg>
              <div class="btn-text">
                <strong>AirPlay / 屏幕投送</strong>
                <span>HomePod / Apple TV / 局域网 Cast</span>
              </div>
            </button>

            <button class="cast-action-btn secondary" id="rm-btn-copy-stream">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
                <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/>
              </svg>
              <div class="btn-text">
                <strong>复制音频 DLNA 直链</strong>
                <span>适用于智能电视盒子、VLC、Kodi 播放</span>
              </div>
            </button>
          </div>

          <div class="cast-hint-box">
            💡 <strong>投屏技巧</strong>：
            <ul>
              <li><strong>苹果设备</strong>：点击【AirPlay】可直接唤起控制中心投送到客厅音响与电视；</li>
              <li><strong>安卓 / PC</strong>：点击【AirPlay / 屏幕投送】调起原生媒体流，或复制直链发送至电视盒子的 DLNA 接收端。</li>
            </ul>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(castModal);

    // 事件绑定
    const closeBtn = castModal.querySelector(".r-music-cast-close");
    const overlay = castModal.querySelector(".r-music-cast-overlay");
    const hide = () => (castModal.style.display = "none");
    closeBtn.addEventListener("click", hide);
    overlay.addEventListener("click", hide);

    // AirPlay / Cast 按钮逻辑
    const airplayBtn = castModal.querySelector("#rm-btn-airplay");
    airplayBtn.addEventListener("click", () => {
      triggerNativeCast(audio);
    });

    // 复制直链逻辑
    const copyBtn = castModal.querySelector("#rm-btn-copy-stream");
    copyBtn.addEventListener("click", () => {
      const src = audio.currentSrc || audio.src;
      if (!src) {
        alert("当前没有正在播放的音频流");
        return;
      }
      navigator.clipboard.writeText(src).then(() => {
        const statusEl = castModal.querySelector("#rm-cast-track-status");
        statusEl.innerHTML = "<span style='color:#00F2FE;'>✓ 已成功复制高音质音频直链到剪贴板！</span>";
        setTimeout(() => {
          statusEl.innerText = "可在电视播放器或局域网播放端粘贴直接播放";
        }, 3000);
      });
    });

    return castModal;
  }

  function triggerNativeCast(audio) {
    if (!audio) {
      alert("未检测到活跃的音频组件");
      return;
    }

    // 1. WebKit / Safari AirPlay
    if (window.WebKitPlaybackTargetAvailabilityEvent || "webkitShowPlaybackTargetPicker" in audio) {
      try {
        audio.webkitShowPlaybackTargetPicker();
        return;
      } catch (e) {
        console.warn("[R-Music] AirPlay picker failed:", e);
      }
    }

    // 2. Chromium / Edge Remote Playback API
    if (audio.remote && typeof audio.remote.prompt === "function") {
      audio.remote.prompt().then(() => {
        console.log("[R-Music] Remote Playback connected successfully.");
      }).catch((err) => {
        console.log("[R-Music] Remote Playback prompt error:", err);
        alert("请在浏览器弹出的投屏选项中选择您的电视或音响设备。如果未发现设备，请确保设备在同一 Wi-Fi 下。");
      });
      return;
    }

    alert("当前浏览器暂未开启原生 AirPlay/Cast，请使用【复制音频 DLNA 直链】在电视端直接点播。");
  }

  function injectCastButton() {
    const player = document.querySelector(".player");
    if (!player || document.querySelector(".r-music-cast-trigger")) return;

    // 获取网页中的全局 audio 标签
    const audio = document.querySelector("audio");
    if (audio) {
      audio.setAttribute("x-webkit-airplay", "allow");
      audio.setAttribute("airplay", "allow");
    }

    const castModal = createCastModal(audio);

    // 创建投屏按钮
    const btn = document.createElement("button");
    btn.className = "r-music-cast-trigger";
    btn.title = "投屏 (AirPlay & DLNA)";
    btn.innerHTML = `
      <svg class="cast-btn-svg" viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
        <path d="M1 18v3h3c0-1.66-1.34-3-3-3zm0-4v2c2.76 0 5 2.24 5 5h2c0-3.87-3.13-7-7-7zm0-4v2c4.97 0 9 4.03 9 9h2c0-6.08-4.92-11-11-11zm20-7H3c-1.1 0-2 .9-2 2v3h2V5h18v14h-7v2h7c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z"/>
      </svg>
      <span class="cast-status-indicator"></span>
    `;

    btn.addEventListener("click", () => {
      // 更新曲目信息
      const titleEl = document.querySelector(".player .title") || document.querySelector(".player .track-info .title");
      const artistEl = document.querySelector(".player .artist") || document.querySelector(".player .track-info .artist");
      const name = titleEl ? titleEl.innerText : "当前播放歌曲";
      const artist = artistEl ? artistEl.innerText : "";

      document.getElementById("rm-cast-track-name").innerText = `${name} ${artist ? ' - ' + artist : ''}`;
      castModal.style.display = "flex";
    });

    // 优先插入到右侧额外控制区 (音量前或播放列表旁)
    const extraControls = player.querySelector(".extra-control") || player.querySelector(".controls");
    if (extraControls) {
      extraControls.appendChild(btn);
    } else {
      player.appendChild(btn);
    }

    console.log("[R-Music] Cast Button injected into Player successfully.");
  }

  // 3. 轮询监控 DOM 渲染并维持注入
  function loopInit() {
    injectBrandLogo();
    injectCastButton();
  }

  // 初始化执行并挂载监听器
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loopInit);
  } else {
    loopInit();
  }

  // 定时器确保 SPA 路由跳转后控件依然存在
  setInterval(loopInit, 1500);

})();
