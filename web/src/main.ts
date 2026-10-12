import { createApp } from "vue";
import { createPinia } from "pinia";
import router from "./router";
import App from "./App.vue";
import "./style.css";

/** 主题：跟随系统，允许本地覆盖（存 localStorage 的 "theme": light/dark/system） */
function applyTheme() {
  const saved = localStorage.getItem("theme") || "system";
  const dark = saved === "dark" ||
    (saved === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
applyTheme();
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  if ((localStorage.getItem("theme") || "system") === "system") applyTheme();
});

createApp(App).use(createPinia()).use(router).mount("#app");

// PWA：注册 service worker（离线外壳 + 静态资源缓存；音频/接口永不缓存）
// URL 带构建时间戳：Cloudflare 按完整 URL 做缓存键，SW 每次发版都是新地址，
// 不会被边缘上旧的 immutable 缓存副本卡住。
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`/sw.js?v=${__BUILD_TS__}`).catch(() => {});
  });
}
