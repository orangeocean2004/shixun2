<script setup>
import { onMounted, reactive, ref } from 'vue'
import { getModelSettings, updateModelSettings } from '../api/settings'

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const form = reactive({
  OPENAI_API_KEY: '',
  OPENAI_BASE_URL: '',
  LLM_MODEL: '',
})

async function loadSettings() {
  loading.value = true
  error.value = ''
  success.value = ''
  try {
    const data = await getModelSettings()
    form.OPENAI_API_KEY = data.OPENAI_API_KEY || ''
    form.OPENAI_BASE_URL = data.OPENAI_BASE_URL || ''
    form.LLM_MODEL = data.LLM_MODEL || ''
  } catch (e) {
    error.value = e?.message || '加载设置失败'
  } finally {
    loading.value = false
  }
}

async function saveSettings() {
  error.value = ''
  success.value = ''

  const payload = {
    OPENAI_API_KEY: (form.OPENAI_API_KEY || '').trim(),
    OPENAI_BASE_URL: (form.OPENAI_BASE_URL || '').trim(),
    LLM_MODEL: (form.LLM_MODEL || '').trim(),
  }

  if (!payload.OPENAI_BASE_URL) {
    error.value = 'OPENAI_BASE_URL 不能为空。'
    return
  }
  if (!payload.LLM_MODEL) {
    error.value = 'LLM_MODEL 不能为空。'
    return
  }

  saving.value = true
  try {
    const saved = await updateModelSettings(payload)
    form.OPENAI_API_KEY = saved.OPENAI_API_KEY || ''
    form.OPENAI_BASE_URL = saved.OPENAI_BASE_URL || ''
    form.LLM_MODEL = saved.LLM_MODEL || ''
    success.value = '模型配置已保存。'
  } catch (e) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="settings-layout">
    <section class="panel settings-panel">
      <h2>模型设置</h2>
      <p class="hint">修改后会由后端持久化为 JSON，并在运行时用于问答与 QA 合成。</p>

      <p v-if="loading" class="loading">正在加载设置...</p>
      <p v-if="error" class="error">{{ error }}</p>
      <p v-if="success" class="success">{{ success }}</p>

      <form class="settings-form" @submit.prevent="saveSettings">
        <label class="field" for="api-key">
          <span>OPENAI_API_KEY</span>
          <input
            id="api-key"
            v-model="form.OPENAI_API_KEY"
            type="password"
            placeholder="sk-..."
            autocomplete="off"
          />
        </label>

        <label class="field" for="base-url">
          <span>OPENAI_BASE_URL</span>
          <input
            id="base-url"
            v-model="form.OPENAI_BASE_URL"
            type="text"
            placeholder="https://api.deepseek.com"
          />
        </label>

        <label class="field" for="model-name">
          <span>LLM_MODEL</span>
          <input
            id="model-name"
            v-model="form.LLM_MODEL"
            type="text"
            placeholder="deepseek-chat"
          />
        </label>

        <div class="actions">
          <button type="button" class="ghost-btn" :disabled="loading || saving" @click="loadSettings">
            重新加载
          </button>
          <button type="submit" class="save-btn" :disabled="loading || saving">
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.settings-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-surface);
  box-shadow: var(--shadow-soft);
}

.panel:hover {
  border-color: var(--border-strong);
}

.settings-panel h2 {
  margin: 0;
}

.hint {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.settings-form {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.field input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 14px;
  background: var(--bg-surface-2);
  color: var(--text-primary);
}

.field input::placeholder {
  color: var(--text-muted);
}

.field input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(var(--accent-rgb), 0.25);
}

.actions {
  margin-top: 4px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.ghost-btn,
.save-btn {
  border: 1px solid rgba(var(--accent-rgb), 0.38);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.26), rgba(var(--accent-rgb), 0.12));
  padding: 8px 12px;
  font-size: 14px;
  color: #eaf2ff;
  font-weight: 600;
  cursor: pointer;
}

.ghost-btn:hover:not(:disabled),
.save-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.4), rgba(var(--accent-rgb), 0.2));
}

.ghost-btn:disabled,
.save-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.loading {
  margin: 12px 0 0;
  color: var(--accent);
}

.error {
  margin: 12px 0 0;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid rgba(230, 127, 104, 0.5);
  border-radius: 8px;
  padding: 10px;
}

.success {
  margin: 12px 0 0;
  color: #6fe1bc;
  background: rgba(111, 225, 188, 0.1);
  border: 1px solid rgba(111, 225, 188, 0.35);
  border-radius: 8px;
  padding: 10px;
}
</style>
