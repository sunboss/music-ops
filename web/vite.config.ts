import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// 生产构建输出到 ../dist（nginx 直接挂载），/api 由 nginx 反代到增强服务
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  // __BUILD_TS__：构建时间戳，用于 SW 注册 URL 防 Cloudflare 边缘旧缓存
  define: { __BUILD_TS__: JSON.stringify(Date.now()) },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    outDir: "../dist-new",
    emptyOutDir: true,
    target: "es2020",
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["vue", "vue-router", "pinia"],
          audio: ["howler"],
        },
      },
    },
  },
  server: {
    port: 5180,
    proxy: { "/api": { target: "http://127.0.0.1:3001", changeOrigin: true } },
  },
});
