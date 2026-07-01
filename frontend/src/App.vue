<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'

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
        <div class="header-copy">
          <span class="eyebrow">RAG Chunking Studio</span>
          <h1>面向 RAG 的智能分段 Demo</h1>
          <p>上传文档、观察分块效果，并快速验证问答与 QA 合成结果。</p>
        </div>
        <div class="header-actions">
          <nav class="main-nav">
            <RouterLink class="nav-link" to="/">首页</RouterLink>
            <RouterLink class="nav-link" to="/settings">设置</RouterLink>
          </nav>
          <button type="button" class="theme-btn" @click="toggleTheme">
            主题色：{{ currentTheme.label }}
            <span>切换到 {{ nextThemeLabel }}</span>
          </button>
        </div>
      </div>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #11161f;
}

:global(*) {
  box-sizing: border-box;
}

.app-shell {
  --bg-page: #11161f;
  --bg-surface: rgba(27, 34, 46, 0.88);
  --bg-surface-2: rgba(34, 43, 58, 0.94);
  --bg-surface-3: rgba(42, 53, 70, 0.92);
  --bg-code: rgba(19, 26, 36, 0.96);
  --border: rgba(138, 156, 182, 0.18);
  --border-strong: rgba(138, 156, 182, 0.28);
  --border-accent: rgba(66, 133, 244, 0.34);
  --text-primary: #edf2fb;
  --text-secondary: #b9c5d7;
  --text-muted: #8d9aae;
  --accent-rgb: 66, 133, 244;
  --accent: #4285f4;
  --accent-strong: #2f6fda;
  --accent-soft: rgba(var(--accent-rgb), 0.14);
  --accent-softer: rgba(var(--accent-rgb), 0.08);
  --surface-hover: rgba(255, 255, 255, 0.035);
  --success: #73ddb8;
  --success-soft: rgba(115, 221, 184, 0.12);
  --danger: #ef8d77;
  --danger-soft: rgba(239, 141, 119, 0.12);
  --warning: #e0bf72;
  --warning-soft: rgba(224, 191, 114, 0.12);
  --shadow-soft: 0 14px 32px rgba(0, 0, 0, 0.2);
  --shadow-card: 0 10px 24px rgba(0, 0, 0, 0.16);
  --radius-lg: 18px;
  --radius-md: 12px;
  --radius-sm: 10px;
  --transition-fast: 140ms ease;
  --transition-normal: 200ms ease;

  margin: 0 auto;
  max-width: 1280px;
  min-height: 100vh;
  padding: 28px 24px 40px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--text-primary);
  background:
    radial-gradient(circle at top right, rgba(var(--accent-rgb), 0.12), transparent 34%),
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.03), transparent 26%),
    var(--bg-page);
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
  margin-bottom: 22px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 20px;
  flex-wrap: wrap;
  padding: 22px 24px;
  border: 1px solid var(--border);
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.015));
  box-shadow: var(--shadow-soft);
  backdrop-filter: blur(14px);
}

.header-copy {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 720px;
}

.eyebrow {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 6px 10px;
  border: 1px solid rgba(var(--accent-rgb), 0.2);
  border-radius: 999px;
  background: rgba(var(--accent-rgb), 0.1);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.header h1 {
  margin: 0;
  font-size: 30px;
  line-height: 1.15;
  letter-spacing: 0.2px;
}

.header p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.65;
}

.header-actions {
  display: flex;
  align-items: flex-start;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.main-nav {
  display: inline-flex;
  gap: 8px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
}

.nav-link {
  text-decoration: none;
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 700;
  padding: 8px 14px;
  transition:
    background-color var(--transition-fast),
    color var(--transition-fast),
    box-shadow var(--transition-normal);
}

.nav-link:hover {
  color: #ffffff;
  background: rgba(var(--accent-rgb), 0.12);
}

.nav-link.router-link-exact-active {
  color: #ffffff;
  background: rgba(var(--accent-rgb), 0.22);
  box-shadow: inset 0 0 0 1px rgba(var(--accent-rgb), 0.24);
}

.theme-btn {
  display: inline-flex;
  flex-direction: column;
  gap: 3px;
  min-width: 156px;
  border: 1px solid rgba(var(--accent-rgb), 0.26);
  border-radius: 16px;
  background: rgba(var(--accent-rgb), 0.12);
  color: #f5f9ff;
  font-size: 13px;
  font-weight: 700;
  padding: 10px 14px;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition:
    transform var(--transition-normal),
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    box-shadow var(--transition-normal);
}

.theme-btn span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
}

.theme-btn:hover {
  border-color: rgba(var(--accent-rgb), 0.42);
  background: rgba(var(--accent-rgb), 0.16);
  transform: translateY(-1px);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
}

.theme-btn:active {
  transform: scale(0.99);
}

.app-main {
  display: flex;
  flex-direction: column;
}

:deep(.panel) {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.028), rgba(255, 255, 255, 0.012));
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(10px);
}

:deep(.panel:hover) {
  border-color: var(--border-strong);
}

:deep(.panel-title) {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
}

:deep(.panel-subtitle) {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

:deep(.ui-field) {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

:deep(.ui-field-title) {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

:deep(.ui-field-help) {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

:deep(.ui-input) {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 11px 12px;
  background: rgba(255, 255, 255, 0.028);
  color: var(--text-primary);
  font-size: 14px;
  transition:
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    box-shadow var(--transition-normal),
    transform var(--transition-normal);
}

:deep(.ui-input::placeholder) {
  color: var(--text-muted);
}

:deep(.ui-input:hover) {
  background: rgba(255, 255, 255, 0.045);
}

:deep(.ui-input:focus) {
  border-color: rgba(var(--accent-rgb), 0.48);
  box-shadow: 0 0 0 4px rgba(var(--accent-rgb), 0.14);
  outline: none;
}

:deep(input[type='file'].ui-input) {
  padding: 9px 12px;
}

:deep(.ui-button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition:
    transform var(--transition-normal),
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    box-shadow var(--transition-normal),
    color var(--transition-fast);
}

:deep(.ui-button:hover:not(:disabled)) {
  transform: translateY(-1px);
}

:deep(.ui-button:active:not(:disabled)) {
  transform: scale(0.99);
}

:deep(.ui-button:disabled) {
  opacity: 0.45;
  cursor: not-allowed;
  box-shadow: none;
}

:deep(.ui-button--primary) {
  border-color: rgba(var(--accent-rgb), 0.28);
  background: linear-gradient(180deg, rgba(var(--accent-rgb), 0.24), rgba(var(--accent-rgb), 0.18));
  color: #f7fbff;
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.16);
}

:deep(.ui-button--primary:hover:not(:disabled)) {
  border-color: rgba(var(--accent-rgb), 0.4);
  background: linear-gradient(180deg, rgba(var(--accent-rgb), 0.3), rgba(var(--accent-rgb), 0.22));
}

:deep(.ui-button--secondary) {
  border-color: var(--border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-primary);
}

:deep(.ui-button--secondary:hover:not(:disabled)) {
  border-color: var(--border-strong);
  background: rgba(255, 255, 255, 0.05);
}

:deep(.ui-button--ghost) {
  padding-inline: 12px;
  border-color: transparent;
  background: transparent;
  color: var(--text-secondary);
}

:deep(.ui-button--ghost:hover:not(:disabled)) {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.05);
}

:deep(.ui-status) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  border: 1px solid transparent;
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 14px;
  line-height: 1.5;
}

:deep(.ui-status--error) {
  color: var(--danger);
  background: var(--danger-soft);
  border-color: rgba(239, 141, 119, 0.28);
}

:deep(.ui-status--success) {
  color: var(--success);
  background: var(--success-soft);
  border-color: rgba(115, 221, 184, 0.24);
}

:deep(.ui-status--loading) {
  color: var(--accent);
  background: var(--accent-softer);
  border-color: rgba(var(--accent-rgb), 0.22);
}

:deep(.ui-pill) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.2;
}

:deep(.ui-pill--accent) {
  border-color: rgba(var(--accent-rgb), 0.22);
  background: rgba(var(--accent-rgb), 0.12);
  color: var(--text-primary);
}

:deep(.ui-pill--success) {
  border-color: rgba(115, 221, 184, 0.22);
  background: rgba(115, 221, 184, 0.12);
  color: var(--success);
}

:deep(.ui-pill--warning) {
  border-color: rgba(224, 191, 114, 0.24);
  background: rgba(224, 191, 114, 0.12);
  color: var(--warning);
}

:deep(.ui-code) {
  margin: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px;
  background: var(--bg-code);
  color: var(--text-secondary);
  overflow: auto;
}

:deep(button:focus-visible),
:deep(input:focus-visible),
:deep(textarea:focus-visible),
:deep(select:focus-visible) {
  outline: 2px solid rgba(var(--accent-rgb), 0.55);
  outline-offset: 2px;
}

@media (max-width: 960px) {
  .app-shell {
    padding: 20px 16px 32px;
  }

  .header-top {
    padding: 18px;
  }

  .header h1 {
    font-size: 26px;
  }

  .header-actions {
    width: 100%;
    justify-content: space-between;
  }
}

@media (max-width: 720px) {
  .main-nav {
    width: 100%;
    justify-content: space-between;
  }

  .nav-link {
    flex: 1;
    text-align: center;
  }

  .theme-btn {
    width: 100%;
  }
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
