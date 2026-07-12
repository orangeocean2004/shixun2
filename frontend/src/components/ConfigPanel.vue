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
const autoMode = ref(true)

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
    minChars: autoMode.value ? 300 : Number(form.minChars),
    targetChars: autoMode.value ? 900 : Number(form.targetChars),
    maxChars: autoMode.value ? 1200 : Number(form.maxChars),
    overlapSentences: autoMode.value ? 1 : Number(form.overlapSentences),
  })
}
</script>

<template>
  <section class="panel config-panel">
    <div class="config-header">
      <div>
        <h2 class="panel-title">上传与分段配置</h2>
        <p class="panel-subtitle">先选择文档，系统会自动根据文档长度选择最优分段参数。</p>
      </div>
    </div>

    <div class="config-section">
      <div class="config-grid config-grid--primary">
        <label class="ui-field config-field">
          <span class="ui-field-title">文档文件 <span class="ui-tip" tabindex="0" data-tip="选择要进行分段处理的文档文件。">ⓘ</span></span>
          <input class="ui-input" type="file" @change="onFileChange" :disabled="props.loading" />
          <span class="ui-field-help">支持 .pdf .txt .md .docx .jsonl 格式</span>
        </label>

        <label class="ui-field config-field">
          <span class="ui-field-title">文档标识 <span class="ui-tip" tabindex="0" data-tip="文档唯一标识；留空时默认使用文件名生成。">ⓘ</span></span>
          <input class="ui-input" v-model="form.docId" type="text" placeholder="默认使用文件名" :disabled="props.loading" />
          <span class="ui-field-help">可选，用于覆盖默认生成的 doc_id。</span>
        </label>
      </div>
    </div>

    <div class="config-section config-section--secondary">
      <div class="section-heading">
        <div class="section-heading-row">
          <h3>分段参数 <span class="ui-tip" tabindex="0" data-tip="自动适配会按文档长度选择分段参数；关闭后使用手动参数。">ⓘ</span></h3>
          <label class="toggle-label">
            <input type="checkbox" v-model="autoMode" :disabled="props.loading" />
            <span class="toggle-track">
              <span class="toggle-thumb"></span>
            </span>
            <span class="toggle-text">{{ autoMode ? '自动适配' : '手动设置' }}</span>
          </label>
        </div>
        <p v-if="autoMode" class="auto-desc">
          根据文档总长度自动选择参数：短文档用小块保证精度，长文档用大块避免碎片化。
        </p>
        <p v-else class="auto-desc manual-hint">
          手动调整参数，修改任意值后将完全按此配置执行分段。
        </p>
      </div>

      <div v-if="autoMode" class="auto-tiers">
        <div class="tier-card">
          <span class="tier-range">&lt; 3K 字符</span>
          <span class="tier-value">小块 · 350 字目标</span>
        </div>
        <div class="tier-card">
          <span class="tier-range">3K ~ 10K</span>
          <span class="tier-value">中块 · 600 字目标</span>
        </div>
        <div class="tier-card">
          <span class="tier-range">10K ~ 50K</span>
          <span class="tier-value">大块 · 700 字目标</span>
        </div>
        <div class="tier-card">
          <span class="tier-range">&gt; 50K 字符</span>
          <span class="tier-value">超大块 · 800~900 字目标</span>
        </div>
      </div>

      <div v-else class="config-grid config-grid--metrics">
        <label class="ui-field config-field">
          <span class="ui-field-title">最小长度 <span class="ui-tip" tabindex="0" data-tip="分段后每个 chunk 的最小字符数下限。">ⓘ</span></span>
          <span class="ui-field-help">min_chars</span>
          <input class="ui-input" v-model.number="form.minChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">目标长度 <span class="ui-tip" tabindex="0" data-tip="分段期望字符数，算法会尽量贴近该值。">ⓘ</span></span>
          <span class="ui-field-help">target_chars</span>
          <input class="ui-input" v-model.number="form.targetChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">最大长度 <span class="ui-tip" tabindex="0" data-tip="分段后每个 chunk 的最大字符数上限。">ⓘ</span></span>
          <span class="ui-field-help">max_chars</span>
          <input class="ui-input" v-model.number="form.maxChars" type="number" min="1" :disabled="props.loading" />
        </label>
        <label class="ui-field config-field">
          <span class="ui-field-title">重叠句数 <span class="ui-tip" tabindex="0" data-tip="相邻 chunk 保留的重叠句子数，用于减少上下文断裂。">ⓘ</span></span>
          <span class="ui-field-help">overlap_sentences</span>
          <input class="ui-input" v-model.number="form.overlapSentences" type="number" min="0" :disabled="props.loading" />
        </label>
      </div>
    </div>

    <div class="config-actions">
      <p class="config-footnote">{{ autoMode ? '自动适配模式：后端根据文档长度选择最优参数。' : '手动模式：完全按你设置的参数分段。' }}</p>
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

.section-heading-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.section-heading h3,
.section-heading p {
  margin: 0;
}

.section-heading h3 {
  font-size: 15px;
}

.auto-desc {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
  margin: 4px 0 0;
}

.manual-hint {
  color: var(--warning);
}

/* ── Toggle switch ── */
.toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}

.toggle-label input {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}

.toggle-track {
  position: relative;
  width: 44px;
  height: 24px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  transition: background var(--transition-fast);
}

.toggle-label input:checked + .toggle-track {
  background: rgba(var(--accent-rgb), 0.45);
}

.toggle-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform var(--transition-fast);
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

.toggle-label input:checked + .toggle-track .toggle-thumb {
  transform: translateX(20px);
}

.toggle-text {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

/* ── Auto tiers ── */
.auto-tiers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 8px;
}

.tier-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
}

.tier-range {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 700;
}

.tier-value {
  font-size: 13px;
  color: var(--text-secondary);
}

.ui-tip {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  margin-left: 6px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1;
  cursor: help;
}

.ui-tip::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  min-width: 200px;
  max-width: 320px;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--border-strong);
  background: rgba(18, 22, 30, 0.96);
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.45;
  white-space: normal;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  z-index: 20;
}

.ui-tip:hover::after,
.ui-tip:focus-visible::after {
  opacity: 1;
  visibility: visible;
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
