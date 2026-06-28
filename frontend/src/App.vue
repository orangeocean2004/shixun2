<script setup>
import { computed, ref } from 'vue'

const themes = [
  {
    key: 'mint',
    label: '薄荷绿',
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
  background: #0d1110;
}

.app-shell {
  --bg-page: #0d1110;
  --bg-surface: #151a18;
  --bg-surface-2: #1d2522;
  --bg-code: #121614;
  --border: #2a3531;
  --border-strong: #3a4742;
  --text-primary: #e5ece8;
  --text-secondary: #a7b2ad;
  --text-muted: #7e8a84;
  --accent-rgb: 51, 199, 155;
  --accent: #33c79b;
  --accent-strong: #27ad86;
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
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 6px 12px;
  cursor: pointer;
}

.theme-btn:hover {
  border-color: var(--accent);
  color: var(--text-primary);
  background: var(--accent-soft);
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
