<script setup lang="ts">
defineProps<{ title: string; more?: string }>();
const emit = defineEmits<{ (e: "more"): void }>();
</script>

<template>
  <section class="sec">
    <div class="hd">
      <h3>{{ title }}</h3>
      <button v-if="more" @click="emit('more')">{{ more }} ›</button>
    </div>
    <slot />
  </section>
</template>

<style scoped>
.sec { padding: 18px 22px 4px; }
.hd { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 12px; }
h3 { font-size: 19px; font-weight: 700; letter-spacing: -.018em; }
button { font-size: 13px; color: var(--acc); }
@media (max-width: 640px) { .sec { padding: 16px 14px 2px; } h3 { font-size: 17.5px; } }
</style>
