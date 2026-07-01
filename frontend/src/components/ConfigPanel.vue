<script setup>
import { reactive, ref } from 'vue'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['submit'])

const file = ref(null)
const form = reactive({
  docId: '',
  minChars: 300,
  targetChars: 900,
  maxChars: 1200,
  overlapSentences: 1,
})

function onFileChange(event) {
  file.value = event.target.files?.[0] || null
}

function onSubmit() {
  if (!file.value) {
    return
  }

  emit('submit', {
    file: file.value,
    docId: form.docId,
    minChars: Number(form.minChars),
    targetChars: Number(form.targetChars),
    maxChars: Number(form.maxChars),
    overlapSentences: Number(form.overlapSentences),
  })
}
</script>

<template>
  <section class="panel config-panel">
    <div class="config-header">
      <div>
        <h2 class="panel-title">上传与分段配置</h2>
        <p class="panel-subtitle">先选择文档，再按需要调整分段长度参数。</p>
      </div>
      <span class="config-tip">建议先用默认参数预览一次效果。</span>
    </div>

    <div class="config-section">
      <div class="config-grid config-grid--primary">
        <label class="ui-field config-field">
          <span class="ui-field-title">文档文件</span>
          <input class="ui-input" type="file" @change="onFileChange" :disabled="props.loading" />
          <span class="ui-field-help">支持上传待分段的原始文档文件。</span>
        </label>

        <label class="ui-field config-field">
          <span class="ui-field-title">文档标识</span>
          <input class="ui-input" v-model="form.docId" type="text" placeholder="默认使用文件名" :disabled="props.loading" />
          <span class="ui-field-help">可选，用于覆盖默认生成的 doc_id。</span>
        </label>
      </div>
    </div>

    <div class="config-section config-section--secondary">
      <div class="section-heading">
        <h3>分段参数</h3>
        <p>这些参数会影响每个 chunk 的目标长度和上下文衔接。</p>
      </div>

      <div class="config-grid config-grid--metrics">
        <label class="ui-field config-field">
          <span class="ui-field-title">最小长度</span>
          <span class="ui-field-help">min_chars</span>
          <input class="ui-input" v-model.number="form.minChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">目标长度</span>
          <span class="ui-field-help">target_chars</span>
          <input class="ui-input" v-model.number="form.targetChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">最大长度</span>
          <span class="ui-field-help">max_chars</span>
          <input class="ui-input" v-model.number="form.maxChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">重叠句数</span>
          <span class="ui-field-help">overlap_sentences</span>
          <input class="ui-input" v-model.number="form.overlapSentences" type="number" min="0" :disabled="props.loading" />
        </label>
      </div>
    </div>

    <div class="config-actions">
      <p class="config-footnote">上传后会自动返回统计信息、目录与分块详情。</p>
      <button class="ui-button ui-button--primary" :disabled="props.loading || !file" @click="onSubmit">
        {{ props.loading ? '处理中...' : '上传并开始分段' }}
      </button>
    </div>
  </section>
</template>

<style scoped>
.config-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.config-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.config-tip {
  display: inline-flex;
  align-items: center;
  padding: 7px 10px;
  border: 1px solid rgba(var(--accent-rgb), 0.18);
  border-radius: 999px;
  background: rgba(var(--accent-rgb), 0.08);
  color: var(--text-secondary);
  font-size: 12px;
}

.config-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-section--secondary {
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.02);
}

.section-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.section-heading h3,
.section-heading p {
  margin: 0;
}

.section-heading h3 {
  font-size: 15px;
}

.section-heading p {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.config-grid {
  display: grid;
  gap: 14px;
}

.config-grid--primary {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.config-grid--metrics {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.config-field {
  min-width: 0;
}

.config-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.config-footnote {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}

@media (max-width: 720px) {
  .config-actions {
    align-items: stretch;
  }

  .config-actions .ui-button {
    width: 100%;
  }
}
</style>
