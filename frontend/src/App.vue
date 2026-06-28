<script setup>
import { computed, ref } from 'vue'

const themes = [
  {
    key: 'blue',
    label: '深空蓝',
  },
  {
    key: 'amber',
    label: '琥珀橙',
  },
  {
    key: 'coral',
    label: '珊瑚红',
  },
]

const themeIndex = ref(0)

const currentTheme = computed(() => themes[themeIndex.value])
const nextThemeLabel = computed(() => themes[(themeIndex.value + 1) % themes.length].label)

function toggleTheme() {
  themeIndex.value = (themeIndex.value + 1) % themes.length
}
</script>

<template>
  <div class="app-shell" :data-theme="currentTheme.key">
    <header class="header">
      <div class="header-top">
        <h1>面向 RAG 的智能分段 Demo</h1>
        <button type="button" class="theme-btn" @click="toggleTheme">
          主题色：{{ currentTheme.label }} → {{ nextThemeLabel }}
        </button>
      </div>
      <p>上传文档并查看分段结果。</p>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #171c25;
}

.app-shell {
  --bg-page: #171c25;
  --bg-surface: #202734;
  --bg-surface-2: #283142;
  --bg-code: #1d2532;
  --border: #3a4558;
  --border-strong: #4a5870;
  --text-primary: #e8eef8;
  --text-secondary: #b1bdd0;
  --text-muted: #8f9cb2;
  --accent-rgb: 66, 133, 244;
  --accent: #4285f4;
  --accent-strong: #2f6fda;
  --accent-soft: rgba(var(--accent-rgb), 0.16);
  --danger: #e67f68;
  --danger-soft: rgba(230, 127, 104, 0.16);
  --warning: #d8b15b;
  --shadow-soft: 0 10px 24px rgba(0, 0, 0, 0.25);
  --transition-fast: 140ms ease;
  --transition-normal: 200ms ease;

  margin: 0 auto;
  max-width: 1200px;
  min-height: 100vh;
  padding: 24px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--text-primary);
  background: radial-gradient(circle at top right, rgba(var(--accent-rgb), 0.08), transparent 34%), var(--bg-page);
}

.app-shell[data-theme='amber'] {
  --accent-rgb: 216, 177, 91;
  --accent: #d8b15b;
  --accent-strong: #be9845;
}

.app-shell[data-theme='coral'] {
  --accent-rgb: 230, 127, 104;
  --accent: #e67f68;
  --accent-strong: #ca6953;
}

.header {
  margin-bottom: 20px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.header h1 {
  margin: 0;
  font-size: 28px;
  letter-spacing: 0.2px;
}

.header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
}

.theme-btn {
  border: 1px solid rgba(var(--accent-rgb), 0.45);
  border-radius: 999px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.34), rgba(var(--accent-rgb), 0.18));
  color: #f5f9ff;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(var(--accent-rgb), 0.22);
}

.theme-btn:hover {
  border-color: var(--accent);
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.46), rgba(var(--accent-rgb), 0.25));
  color: #ffffff;
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(var(--accent-rgb), 0.3);
}

.theme-btn:active {
  transform: scale(0.985);
}

:deep(button),
:deep(input),
:deep(textarea),
:deep(select),
:deep(.panel),
:deep(.chunk-card),
:deep(.metric-item),
:deep(.qa-item),
:deep(.catalog-item) {
  transition:
    background-color var(--transition-fast),
    border-color var(--transition-fast),
    color var(--transition-fast),
    box-shadow var(--transition-normal),
    transform var(--transition-normal);
}

:deep(button:focus-visible),
:deep(input:focus-visible),
:deep(textarea:focus-visible),
:deep(select:focus-visible) {
  outline: 2px solid rgba(var(--accent-rgb), 0.55);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  :deep(*),
  :deep(*::before),
  :deep(*::after) {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
</style>
