<script setup>
import { computed, ref } from 'vue'
import ConfigPanel from '../components/ConfigPanel.vue'
import MetricPanel from '../components/MetricPanel.vue'
import ChunkList from '../components/ChunkList.vue'
import { queryRetrievedChunks } from '../api/chunking'
import { apiFetch } from '../api/client'
import { useChunkStore } from '../stores/chunkStore'

const { state, submitUpload } = useChunkStore()
const activeTab = ref('result')
const activeCatalogId = ref('')
const resultChunkListRef = ref(null)
const qaChunkListRef = ref(null)
const qaQuestion = ref('')
const qaDocId = ref('')
const qaLoading = ref(false)
const qaError = ref('')
const qaRetrievedChunks = ref([])
const qaAnswer = ref('')
const qaSynthesizing = ref(false)
const qaPairs = ref([])
const qaSynthError = ref('')
const hasResult = computed(() => Boolean(state.result))
const rawResultJson = computed(() => (state.result ? JSON.stringify(state.result, null, 2) : ''))
const rawResultHighlighted = computed(() => highlightJson(rawResultJson.value))

function highlightJson(json) {
  if (!json) {
    return ''
  }

  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(
      /(\"(\\u[\da-fA-F]{4}|\\[^u]|[^\\\"])*\"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
      (match) => {
        let tokenClass = 'json-number'
        if (match.startsWith('"')) {
          tokenClass = match.endsWith(':') ? 'json-key' : 'json-string'
        } else if (match === 'true' || match === 'false') {
          tokenClass = 'json-boolean'
        } else if (match === 'null') {
          tokenClass = 'json-null'
        }
        return `<span class="${tokenClass}">${match}</span>`
      },
    )
}

function normalizeLabelItem(item) {
  if (!item) {
    return ''
  }
  if (typeof item === 'string') {
    return item.trim()
  }
  if (typeof item === 'object') {
    if (typeof item.name === 'string') {
      return item.name.trim()
    }
    if (typeof item.label === 'string') {
      return item.label.trim()
    }
    if (typeof item.value === 'string') {
      return item.value.trim()
    }
  }
  return ''
}

function getChunkLabels(chunk) {
  const source = chunk.labels ?? chunk.label
  if (Array.isArray(source)) {
    return source.map(normalizeLabelItem).filter(Boolean)
  }
  if (typeof source === 'string' && source.trim()) {
    return [source.trim()]
  }
  return []
}

function getCatalogLabel(chunk) {
  const lastTitle = chunk.title_path?.at(-1)
  return lastTitle || chunk.chunk_id
}

function switchTab(tab) {
  if (tab === 'json' && !hasResult.value) {
    return
  }
  activeTab.value = tab
}

function scrollToTop() {
  window.scrollTo({
    top: 0,
    behavior: 'smooth',
  })
}

function jumpToChunk(chunkId, target = 'result') {
  if (target === 'qa') {
    qaChunkListRef.value?.scrollToChunk(chunkId)
    return
  }
  activeTab.value = 'result'
  activeCatalogId.value = chunkId
  resultChunkListRef.value?.scrollToChunk(chunkId)
}

function openAllChunksView(chunk) {
  const docId = chunk.doc_id || qaDocId.value || state.result?.doc_id
  if (!docId) {
    qaError.value = '缺少 doc_id，无法打开全部 chunks。'
    return
  }
  const url = `/api/chunks/all?doc_id=${encodeURIComponent(docId)}`
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function runQuery() {
  qaError.value = ''
  qaRetrievedChunks.value = []

  const question = qaQuestion.value.trim()
  if (!question) {
    qaError.value = '请输入问题。'
    return
  }

  qaLoading.value = true
  try {
    const response = await queryRetrievedChunks({
      question,
    })
    qaDocId.value = response.doc_id || qaDocId.value
    qaRetrievedChunks.value = response.chunks || []
    qaAnswer.value = response.answer || ''
  } catch (error) {
    qaError.value = error?.message || '检索失败，请稍后重试。'
  } finally {
    qaLoading.value = false
  }
}

async function synthesizeQA() {
  if (!state.result?.chunks?.length) return
  qaSynthesizing.value = true
  qaSynthError.value = ''
  qaPairs.value = []
  try {
    const data = await apiFetch('/api/synthesize-qa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chunks: state.result.chunks }),
    })
    qaPairs.value = data.qa_pairs || []
  } catch (e) {
    qaSynthError.value = e?.message || 'QA 合成失败'
  } finally {
    qaSynthesizing.value = false
  }
}

function downloadQAPairs() {
  const lines = qaPairs.value.map(p => JSON.stringify(p)).join('\n')
  const blob = new Blob([lines], { type: 'application/jsonl' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = (state.result?.doc_id || 'qa') + '_qa.jsonl'
  a.click()
  URL.revokeObjectURL(url)
}

function handleSubmit(payload) {
  activeTab.value = 'result'
  activeCatalogId.value = ''
  qaDocId.value = payload.docId || ''
  qaRetrievedChunks.value = []
  qaError.value = ''
  submitUpload(payload)
}

</script>

<template>
  <div class="layout">
    <section class="panel tabs-panel">
      <div class="tabs">
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'qa' }"
          @click="switchTab('qa')"
        >
          问答检索
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'result' }"
          @click="switchTab('result')"
        >
          文档分块
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'qasync' }"
          :disabled="!hasResult"
          @click="switchTab('qasync')"
        >
          QA 合成
        </button>
        <button
          type="button"
          class="tab-btn"
          :class="{ active: activeTab === 'json' }"
          :disabled="!hasResult"
          @click="switchTab('json')"
        >
          原始 JSON
        </button>
      </div>
      <p v-if="!hasResult" class="tabs-hint">请在“文档分块”中上传文档后查看目录与原始 JSON；问答检索可直接使用。</p>
    </section>

    <section v-if="activeTab === 'result'" class="result-tab">
      <ConfigPanel :loading="state.loading" @submit="handleSubmit" />
      <p v-if="state.loading" class="loading">正在处理文档，请稍候...</p>
      <p v-if="state.error" class="error">{{ state.error }}</p>

      <section v-if="hasResult" class="result-layout">
        <aside class="panel catalog-panel">
          <div class="catalog-head">
            <h2>目录</h2>
            <button type="button" class="top-btn" @click="scrollToTop">回到顶部</button>
          </div>
          <div class="catalog-list">
            <button
              v-for="chunk in state.result.chunks"
              :key="chunk.chunk_id"
              type="button"
              class="catalog-item"
              :class="{ active: activeCatalogId === chunk.chunk_id }"
              @click="jumpToChunk(chunk.chunk_id)"
            >
              {{ getCatalogLabel(chunk) }}
            </button>
          </div>
        </aside>

        <div class="result-main">
          <MetricPanel :statistics="state.result.statistics" :strategy="state.result.strategy" />
          <ChunkList ref="resultChunkListRef" :chunks="state.result.chunks" :doc-id="state.result?.doc_id || ''" />
        </div>
      </section>

      <section v-else class="panel empty-panel">
        <p class="empty">请先上传文档后查看分段结果。</p>
      </section>
    </section>

    <section v-else-if="activeTab === 'qa'" class="panel qa-panel">
      <h2>问答检索</h2>
      <div class="qa-form">
        <input v-model="qaQuestion" type="text" placeholder="输入问题，例如：这份文档的核心结论是什么？" @keydown.enter="runQuery" />
        <button type="button" class="tab-btn" :disabled="qaLoading" @click="runQuery">
          {{ qaLoading ? '检索中...' : '提交问题' }}
        </button>
      </div>

      <p v-if="qaError" class="error inline-error">{{ qaError }}</p>

      <div v-if="qaAnswer" class="qa-answer-box">
        <h3>回答</h3>
        <p>{{ qaAnswer }}</p>
      </div>

      <div v-if="qaRetrievedChunks.length" class="qa-result-list">
        <h3>已检索 chunks（{{ qaRetrievedChunks.length }}）</h3>
        <article v-for="chunk in qaRetrievedChunks" :key="chunk.chunk_id" class="qa-item">
          <div>
            <strong>{{ chunk.chunk_id }}</strong>
            <p v-if="getChunkLabels(chunk).length" class="qa-labels">labels: {{ getChunkLabels(chunk).join(', ') }}</p>
            <p class="qa-snippet">{{ chunk.summary || chunk.content || '无摘要' }}</p>
          </div>
          <div class="qa-actions">
            <button type="button" class="tab-btn" @click="jumpToChunk(chunk.chunk_id, 'qa')">定位</button>
            <button type="button" class="tab-btn" @click="openAllChunksView(chunk)">view more</button>
          </div>
        </article>

        <h3>详细信息</h3>
        <ChunkList ref="qaChunkListRef" :chunks="qaRetrievedChunks" :doc-id="qaDocId || state.result?.doc_id || ''" />
      </div>

      <p v-else-if="!qaLoading" class="empty">暂无检索结果</p>
    </section>

    <section v-else-if="activeTab === 'qasync'" class="panel qa-synth-panel">
      <div class="qa-synth-head">
        <h2>QA 对合成</h2>
        <button
          type="button"
          class="synth-btn"
          :disabled="qaSynthesizing || !hasResult"
          @click="synthesizeQA"
        >
          {{ qaSynthesizing ? '生成中...' : '生成 QA 对' }}
        </button>
      </div>
      <p v-if="!hasResult" class="empty">请先在"文档分块"中上传文档。</p>
      <p v-if="qaSynthError" class="error">{{ qaSynthError }}</p>
      <div v-if="qaPairs.length" class="qa-pairs-list">
        <div class="qa-pairs-actions">
          <span>共 {{ qaPairs.length }} 个 QA 对</span>
          <button type="button" class="download-btn" @click="downloadQAPairs">下载 JSONL</button>
        </div>
        <div
          v-for="pair in qaPairs"
          :key="pair.id"
          class="qa-pair-card"
        >
          <div class="qa-meta">
            <span :class="pair.answerable ? 'tag-ok' : 'tag-warn'">
              {{ pair.answerable ? '可答' : '存疑' }}
            </span>
            <span :class="pair.faithful ? 'tag-ok' : 'tag-warn'">
              {{ pair.faithful ? '忠实' : '待核' }}
            </span>
            <span class="qa-score">质量: {{ pair.quality_score }}</span>
            <span class="qa-source">{{ pair.source_chunk_id }}</span>
          </div>
          <p class="qa-question"><strong>Q:</strong> {{ pair.question }}</p>
          <p class="qa-answer"><strong>A:</strong> {{ pair.answer }}</p>
        </div>
      </div>
      <p v-else-if="!qaSynthesizing && hasResult" class="empty">点击按钮生成 QA 对。</p>
    </section>

    <section v-else class="panel">
      <h2>原始 JSON 返回值</h2>
      <pre v-if="hasResult" class="raw-json highlighted-json" v-html="rawResultHighlighted"></pre>
      <p v-else class="empty">请先上传文档后查看原始 JSON。</p>
    </section>
  </div>
</template>

<style scoped>
.layout {
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

.tabs-panel {
  padding: 10px;
}

.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tabs-hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.result-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.result-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.catalog-panel {
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 24px);
  overflow: auto;
}

.catalog-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.catalog-panel h2 {
  margin: 0;
}

.top-btn {
  border: 1px solid rgba(var(--accent-rgb), 0.45);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.34), rgba(var(--accent-rgb), 0.18));
  color: #f5f9ff;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 8px;
  cursor: pointer;
  box-shadow: 0 8px 18px rgba(var(--accent-rgb), 0.2);
}

.top-btn:hover {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.45), rgba(var(--accent-rgb), 0.24));
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(var(--accent-rgb), 0.28);
}

.catalog-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.catalog-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  font-size: 13px;
  padding: 8px 10px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.catalog-item:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.catalog-item.active {
  border-color: var(--accent);
  color: var(--text-primary);
  background: var(--accent-soft);
}

.result-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tab-btn {
  border: 1px solid rgba(var(--accent-rgb), 0.38);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.26), rgba(var(--accent-rgb), 0.12));
  padding: 8px 12px;
  font-size: 14px;
  color: #eaf2ff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 8px 16px rgba(var(--accent-rgb), 0.16);
}

.tab-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.4), rgba(var(--accent-rgb), 0.2));
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(var(--accent-rgb), 0.24);
}

.tab-btn.active {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.58), rgba(var(--accent-rgb), 0.32));
  box-shadow: 0 12px 24px rgba(var(--accent-rgb), 0.3);
}

.tab-btn:active:not(:disabled) {
  transform: translateY(0) scale(0.985);
}

.tab-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.qa-panel h2 {
  margin-top: 0;
}

.qa-form {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}

.qa-form input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
  background: var(--bg-surface-2);
  color: var(--text-primary);
}

.qa-form input::placeholder {
  color: var(--text-muted);
}

.qa-form input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(var(--accent-rgb), 0.28);
}

.qa-answer-box {
  margin: 16px 0;
  padding: 16px;
  border: 1px solid rgba(var(--accent-rgb), 0.3);
  border-radius: 10px;
  background: rgba(var(--accent-rgb), 0.06);
}

.qa-answer-box h3 {
  margin: 0 0 8px;
  font-size: 14px;
  color: var(--accent);
}

.qa-answer-box p {
  margin: 0;
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-primary);
}

.inline-error {
  margin-bottom: 10px;
}

.qa-result-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.qa-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
  background: var(--bg-surface-2);
}

.qa-item:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.qa-labels {
  margin: 6px 0 0;
  color: var(--accent);
  font-size: 12px;
}

.qa-snippet {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  max-width: 620px;
}

.qa-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.empty {
  margin: 0;
  color: var(--text-muted);
}

.raw-json {
  margin: 0;
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow: auto;
  max-height: 60vh;
}

.highlighted-json {
  background: var(--bg-code);
  border-color: var(--border-strong);
  color: var(--text-secondary);
  line-height: 1.55;
}

.highlighted-json :deep(.json-key) {
  color: var(--warning);
}

.highlighted-json :deep(.json-string) {
  color: #6fe1bc;
}

.highlighted-json :deep(.json-number) {
  color: #f0a872;
}

.highlighted-json :deep(.json-boolean) {
  color: #9fdc7c;
}

.highlighted-json :deep(.json-null) {
  color: var(--danger);
}

.loading {
  margin: 0;
  color: var(--accent);
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.loading::before {
  content: '';
  width: 12px;
  height: 12px;
  border: 2px solid rgba(51, 199, 155, 0.35);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.error {
  margin: 0;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid rgba(230, 127, 104, 0.5);
  border-radius: 8px;
  padding: 10px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 960px) {
  .result-layout {
    grid-template-columns: 1fr;
  }

  .catalog-panel {
    position: static;
    max-height: none;
  }

  .qa-form {
    grid-template-columns: 1fr;
  }

  .qa-item {
    flex-direction: column;
  }
}

.qa-synth-panel {
  margin-top: 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-surface);
}

.qa-synth-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.qa-synth-head h3 {
  margin: 0;
  font-size: 16px;
}

.synth-btn {
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #7c3aed, #4f46e5);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  font-size: 14px;
}

.synth-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.synth-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
}

.qa-pairs-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.download-btn {
  padding: 6px 14px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
}

.download-btn:hover {
  background: rgba(var(--accent-rgb), 0.12);
}

.qa-pair-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 10px;
  background: var(--bg-surface-2);
}

.qa-meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
  font-size: 12px;
}

.tag-ok {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
  padding: 2px 8px;
  border-radius: 4px;
}

.tag-warn {
  background: rgba(234, 179, 8, 0.15);
  color: #facc15;
  padding: 2px 8px;
  border-radius: 4px;
}

.qa-score {
  color: var(--text-muted);
}

.qa-source {
  color: var(--text-muted);
  font-family: monospace;
  font-size: 11px;
}

.qa-question {
  margin: 0 0 6px;
  font-size: 14px;
  line-height: 1.5;
}

.qa-answer {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>
