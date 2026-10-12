import { createRouter, createWebHistory } from "vue-router";

/** URL 结构与旧站保持一致，老链接与收藏不失效 */
const routes = [
  { path: "/", name: "home", component: () => import("@/views/HomeView.vue") },
  { path: "/explore", name: "explore", component: () => import("@/views/ExploreView.vue") },
  { path: "/library", name: "library", component: () => import("@/views/LibraryView.vue") },
  { path: "/ai", name: "ai", component: () => import("@/views/AIView.vue") },
  { path: "/fm", name: "fm", component: () => import("@/views/FMView.vue") },
  { path: "/playlist/:id", name: "playlist", component: () => import("@/views/PlaylistView.vue") },
  { path: "/album/:id", name: "album", component: () => import("@/views/AlbumView.vue") },
  { path: "/artist/:id", name: "artist", component: () => import("@/views/ArtistView.vue") },
  { path: "/search/:keywords?", name: "search", component: () => import("@/views/SearchView.vue") },
  { path: "/daily/songs", name: "daily", component: () => import("@/views/DailyView.vue") },
  { path: "/settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
  { path: "/:pathMatch(.*)*", name: "notfound", component: () => import("@/views/NotFound.vue") },
];

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});
