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
      <div class="settings-head">
        <div>
          <h2 class="panel-title">模型设置</h2>
          <p class="panel-subtitle">修改后会由后端持久化为 JSON，并在问答检索与 QA 合成时生效。</p>
        </div>
        <span class="ui-pill">运行时配置</span>
      </div>

      <p v-if="loading" class="ui-status ui-status--loading">正在加载设置...</p>
      <p v-if="error" class="ui-status ui-status--error">{{ error }}</p>
      <p v-if="success" class="ui-status ui-status--success">{{ success }}</p>

      <form class="settings-form" @submit.prevent="saveSettings">
        <label class="ui-field">
          <span class="ui-field-title">API Key</span>
          <span class="ui-field-help">OPENAI_API_KEY</span>
          <input
            class="ui-input"
            v-model="form.OPENAI_API_KEY"
            type="password"
            placeholder="sk-..."
            autocomplete="off"
          />
        </label>

        <label class="ui-field">
          <span class="ui-field-title">模型服务地址</span>
          <span class="ui-field-help">OPENAI_BASE_URL</span>
          <input
            class="ui-input"
            v-model="form.OPENAI_BASE_URL"
            type="text"
            placeholder="https://api.deepseek.com"
          />
        </label>

        <label class="ui-field">
          <span class="ui-field-title">模型名称</span>
          <span class="ui-field-help">LLM_MODEL</span>
          <input
            class="ui-input"
            v-model="form.LLM_MODEL"
            type="text"
            placeholder="deepseek-chat"
          />
        </label>

        <div class="actions">
          <button type="button" class="ui-button ui-button--secondary" :disabled="loading || saving" @click="loadSettings">
            重新加载
          </button>
          <button type="submit" class="ui-button ui-button--primary" :disabled="loading || saving">
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

.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.settings-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.settings-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.actions {
  margin-top: 4px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 720px) {
  .actions {
    justify-content: stretch;
  }

  .actions .ui-button {
    width: 100%;
  }
}
</style>
