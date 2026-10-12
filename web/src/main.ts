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
