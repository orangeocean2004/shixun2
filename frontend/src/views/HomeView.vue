<script setup>
import { computed, ref } from 'vue'
import { marked } from 'marked'
import ConfigPanel from '../components/ConfigPanel.vue'
import MetricPanel from '../components/MetricPanel.vue'
import ChunkList from '../components/ChunkList.vue'
import { queryRetrievedChunks } from '../api/chunking'
import { apiFetch } from '../api/client'
import { useChunkStore } from '../stores/chunkStore'

function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

const { state, submitUpload } = useChunkStore()
const activeTab = ref('result')
const activeCatalogId = ref('')
const resultChunkListRef = ref(null)
const qaChunkListRef = ref(null)
const qaQuestion = ref('')
const qaDocId = ref('')
const qaSearchScope = ref('current')
const qaLoading = ref(false)
const qaError = ref('')
const qaRetrievedChunks = ref([])
const qaAnswer = ref('')
const qaSynthesizing = ref(false)
const qaPairs = ref([])
const qaSynthError = ref('')
const qaSaveMode = ref('replace')
const qaGenerateCount = ref(10)
const qaSavedCount = ref(null)
const qaMatched = ref(null)
const qaAnswerCovered = ref(null)
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
      /("(\\u[\da-fA-F]{4}|\\[^u]|[^\\"])*"(\s*:)?|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?)/g,
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
  if ((tab === 'json' || tab === 'eval' || tab === 'qasync' || tab === 'qa') && !hasResult.value) {
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
    qaError.value = '缺少 doc_id，无法查看完整分块。'
    return
  }
  const url = `/api/chunks/all?doc_id=${encodeURIComponent(docId)}`
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function runQuery() {
  qaError.value = ''
  qaRetrievedChunks.value = []
  qaMatched.value = null
  qaAnswerCovered.value = null

  const question = qaQuestion.value.trim()
  if (!question) {
    qaError.value = '请输入问题。'
    return
  }

  qaLoading.value = true
  try {
    const response = await queryRetrievedChunks({
      question,
      docId:
        qaSearchScope.value === 'current'
          ? qaDocId.value || state.result?.doc_id || ''
          : '',
    })
    qaDocId.value = response.doc_id || qaDocId.value
    qaRetrievedChunks.value = response.chunks || []
    qaAnswer.value = response.answer || ''
    qaMatched.value = response.matched_qa || null
    qaAnswerCovered.value = response.answer_covered
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
  qaSavedCount.value = null
  try {
    const data = await apiFetch('/api/synthesize-qa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chunks: state.result.chunks,
        doc_id: state.result?.doc_id || '',
        save_mode: qaSaveMode.value,
        qa_count: qaGenerateCount.value,
      }),
    })
    qaPairs.value = data.qa_pairs || []
    qaSavedCount.value = typeof data.saved === 'number' ? data.saved : null
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
  qaSavedCount.value = null
  submitUpload(payload)
}

</script>

<template>
  <div class="layout">
    <section class="panel tabs-panel">
      <div class="tabs-head">
        <div>
          <h2 class="panel-title">工作台</h2>
          <p class="panel-subtitle">按顺序查看上传结果、问答检索、QA 合成与原始返回数据。</p>
        </div>
        <span class="ui-pill">当前模式：{{ activeTab === 'result' ? '文档分块' : activeTab === 'qasync' ? 'QA 合成' : activeTab === 'qa' ? '问答检索' : '原始 JSON' }}</span>
      </div>
      <div class="tabs">
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
          :class="{ active: activeTab === 'qa' }"
          :disabled="!hasResult"
          @click="switchTab('qa')"
        >
          问答检索
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
      <p v-if="!hasResult" class="tabs-hint">上传文档后可解锁 QA 合成、问答检索与原始 JSON。</p>
    </section>

    <section v-if="activeTab === 'result'" class="result-tab">
      <ConfigPanel :loading="state.loading" :total-chars="state.result?.total_chars || 0" @submit="handleSubmit" />
      <p v-if="state.loading" class="ui-status ui-status--loading">正在处理文档，请稍候...</p>
      <p v-if="state.error" class="ui-status ui-status--error">{{ state.error }}</p>

      <section v-if="hasResult" class="result-layout">
        <aside class="panel catalog-panel">
          <div class="catalog-head">
            <div>
              <h2 class="panel-title">目录</h2>
              <p class="panel-subtitle">点击任一标题可快速定位到对应 chunk。</p>
            </div>
            <button type="button" class="ui-button ui-button--secondary catalog-top-btn" @click="scrollToTop">回到顶部</button>
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
          <MetricPanel :statistics="state.result.statistics" />
          <ChunkList ref="resultChunkListRef" :chunks="state.result.chunks" :doc-id="state.result?.doc_id || ''" />
        </div>
      </section>

      <section v-else class="panel empty-panel">
        <p class="empty-title">还没有分段结果</p>
        <p class="empty">先上传一份文档，即可查看统计信息、目录与分段详情。</p>
      </section>
    </section>

    <section v-else-if="activeTab === 'qa'" class="panel qa-panel">
      <div class="qa-head">
        <div>
          <h2 class="panel-title">问答检索</h2>
          <p class="panel-subtitle">输入问题，快速查看回答与命中的相关分块。</p>
        </div>
        <span class="ui-pill" v-if="qaRetrievedChunks.length">命中 {{ qaRetrievedChunks.length }} 个 chunk</span>
      </div>

      <div class="qa-form">
        <div class="qa-scope-toggle" role="group" aria-label="检索范围">
          <button
            type="button"
            class="qa-scope-option"
            :class="{ active: qaSearchScope === 'current' }"
            @click="qaSearchScope = 'current'"
          >
            仅本次文档
          </button>
          <button
            type="button"
            class="qa-scope-option"
            :class="{ active: qaSearchScope === 'all' }"
            @click="qaSearchScope = 'all'"
          >
            历史全部文档
          </button>
        </div>
        <input
          class="ui-input"
          v-model="qaQuestion"
          type="text"
          placeholder="输入问题，例如：这份文档的核心结论是什么？"
          @keydown.enter="runQuery"
        />
        <button type="button" class="ui-button ui-button--primary" :disabled="qaLoading" @click="runQuery">
          {{ qaLoading ? '检索中...' : '提交问题' }}
        </button>
      </div>

      <p v-if="qaError" class="ui-status ui-status--error">{{ qaError }}</p>

      <div v-if="qaAnswer" class="qa-answer-box">
        <div class="qa-answer-head">
          <h3>回答摘要</h3>
          <div class="qa-answer-badges">
            <span v-if="qaMatched" class="ui-pill ui-pill--success">QA 匹配 ({{ (qaMatched.similarity * 100).toFixed(0) }}%)</span>
            <span v-else class="ui-pill ui-pill--accent">模型生成</span>
            <span v-if="qaAnswerCovered === true" class="ui-pill ui-pill--success">答案已覆盖</span>
            <span v-else-if="qaAnswerCovered === false" class="ui-pill ui-pill--warning">答案未覆盖</span>
          </div>
        </div>
        <p v-if="qaMatched" class="qa-match-source">来源 chunk：{{ qaMatched.chunk_id }}</p>
        <div class="qa-answer-body" v-html="renderMarkdown(qaAnswer)"></div>
      </div>

      <div v-if="qaRetrievedChunks.length" class="qa-result-list">
        <div class="qa-list-head">
          <h3>检索结果</h3>
          <span class="qa-list-note">可先浏览摘要，再跳转到完整分块内容。</span>
        </div>

        <article v-for="chunk in qaRetrievedChunks" :key="chunk.chunk_id" class="qa-item">
          <div class="qa-item-copy">
            <strong>{{ chunk.chunk_id }}</strong>
            <p v-if="getChunkLabels(chunk).length" class="qa-labels">标签：{{ getChunkLabels(chunk).join('、') }}</p>
            <p class="qa-snippet">{{ chunk.summary || chunk.content || '无摘要' }}</p>
          </div>
          <div class="qa-actions">
            <button type="button" class="ui-button ui-button--secondary" @click="jumpToChunk(chunk.chunk_id, 'qa')">定位分块</button>
            <button type="button" class="ui-button ui-button--ghost" @click="openAllChunksView(chunk)">查看完整分块</button>
          </div>
        </article>

        <ChunkList ref="qaChunkListRef" :chunks="qaRetrievedChunks" :doc-id="qaDocId || state.result?.doc_id || ''" />
      </div>

      <p v-else-if="!qaLoading" class="empty">暂无检索结果，输入问题后即可开始。</p>
    </section>

    <section v-else-if="activeTab === 'qasync'" class="panel qa-synth-panel">
      <div class="qa-synth-head">
        <div>
          <h2 class="panel-title">QA 对合成</h2>
          <p class="panel-subtitle">基于当前文档分块自动生成问答对，用于快速抽检质量。</p>
        </div>
        <div class="qa-synth-actions">
          <div class="qa-count-control">
            <span class="qa-count-label">生成个数 <span class="ui-tip" tabindex="0" data-tip="本次最多生成多少个 QA 对。">ⓘ</span></span>
            <input
              class="ui-input qa-count-input"
              v-model.number="qaGenerateCount"
              type="number"
              min="1"
              max="100"
              step="1"
            />
          </div>
          <div class="qa-save-toggle-wrap">
            <span class="qa-save-label">保存方式 <span class="ui-tip" tabindex="0" data-tip="覆盖：先清空该文档已有 QA 对再保存；追加：保留已有 QA 对并在后面新增。">ⓘ</span></span>
            <div class="qa-save-toggle" role="group" aria-label="QA 保存方式">
              <button
                type="button"
                class="qa-save-option"
                :class="{ active: qaSaveMode === 'replace' }"
                @click="qaSaveMode = 'replace'"
              >
                覆盖
              </button>
              <button
                type="button"
                class="qa-save-option"
                :class="{ active: qaSaveMode === 'append' }"
                @click="qaSaveMode = 'append'"
              >
                追加
              </button>
            </div>
          </div>
          <button
            type="button"
            class="ui-button ui-button--primary"
            :disabled="qaSynthesizing || !hasResult"
            @click="synthesizeQA"
          >
            {{ qaSynthesizing ? '生成中...' : '生成 QA 对' }}
          </button>
        </div>
      </div>

      <p v-if="!hasResult" class="empty">请先在“文档分块”中上传文档。</p>
      <p v-if="qaSynthError" class="ui-status ui-status--error">{{ qaSynthError }}</p>
      <p v-if="qaSavedCount !== null" class="ui-status ui-status--success">已保存 {{ qaSavedCount }} 个 QA 对。</p>

      <div v-if="qaPairs.length" class="qa-pairs-list">
        <div class="qa-pairs-actions">
          <span>共 {{ qaPairs.length }} 个 QA 对</span>
          <button type="button" class="ui-button ui-button--secondary" @click="downloadQAPairs">下载 JSONL</button>
        </div>
        <div
          v-for="pair in qaPairs"
          :key="pair.id"
          class="qa-pair-card"
        >
          <div class="qa-meta">
            <span :class="pair.answerable ? 'ui-pill ui-pill--success' : 'ui-pill ui-pill--warning'">
              {{ pair.answerable ? '可答' : '存疑' }}
            </span>
            <span :class="pair.faithful ? 'ui-pill ui-pill--success' : 'ui-pill ui-pill--warning'">
              {{ pair.faithful ? '忠实' : '待核' }}
            </span>
            <span class="ui-pill">质量：{{ pair.quality_score }}</span>
            <span class="ui-pill">来源：{{ pair.source_chunk_id }}</span>
          </div>
          <p class="qa-question"><strong>Q</strong>{{ pair.question }}</p>
          <p class="qa-answer"><strong>A</strong>{{ pair.answer }}</p>
        </div>
      </div>
      <p v-else-if="!qaSynthesizing && hasResult" class="empty">点击上方按钮即可生成 QA 对。</p>
    </section>

    <section v-else class="panel json-panel">
      <div class="json-head">
        <div>
          <h2 class="panel-title">原始 JSON 返回值</h2>
          <p class="panel-subtitle">用于检查后端返回结构和原始字段内容。</p>
        </div>
        <span class="ui-pill">调试视图</span>
      </div>
      <pre v-if="hasResult" class="ui-code raw-json highlighted-json" v-html="rawResultHighlighted"></pre>
      <p v-else class="empty">请先上传文档后查看原始 JSON。</p>
    </section>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.tabs-panel,
.result-tab,
.qa-panel,
.qa-synth-panel,
.json-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tabs-head,
.qa-head,
.qa-synth-head,
.json-head,
.eval-tab-head,
.qa-list-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.qa-count-control {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.qa-count-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
}

.qa-save-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 600;
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
  min-width: 220px;
  max-width: 340px;
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

.qa-count-input {
  width: 88px;
}

.qa-count-input::-webkit-outer-spin-button,
.qa-count-input::-webkit-inner-spin-button {
  opacity: 1;
}


.qa-synth-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}


.qa-save-toggle-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.qa-save-toggle {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
}

.qa-save-option {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  padding: 9px 13px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.qa-save-option.active {
  color: #ffffff;
  background: rgba(var(--accent-rgb), 0.18);
}

.tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tabs-hint,
.qa-list-note {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.result-layout {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 18px;
  align-items: start;
}

.catalog-panel {
  position: sticky;
  top: 12px;
  max-height: calc(100vh - 24px);
  overflow: auto;
  gap: 14px;
}

.catalog-head {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 12px;
}

.catalog-top-btn {
  width: 100%;
}

.catalog-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.catalog-item {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-secondary);
  font-size: 13px;
  padding: 10px 12px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition:
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-normal);
}

.catalog-item:hover {
  border-color: var(--border-strong);
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
}

.catalog-item.active {
  border-color: rgba(var(--accent-rgb), 0.32);
  color: var(--text-primary);
  background: rgba(var(--accent-rgb), 0.12);
}

.result-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.tab-btn {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
  padding: 9px 14px;
  font-size: 14px;
  color: var(--text-secondary);
  font-weight: 700;
  cursor: pointer;
  transition:
    border-color var(--transition-fast),
    background-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-normal);
}

.tab-btn:hover:not(:disabled) {
  border-color: var(--border-strong);
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.045);
  transform: translateY(-1px);
}

.tab-btn.active {
  border-color: rgba(var(--accent-rgb), 0.3);
  color: #ffffff;
  background: rgba(var(--accent-rgb), 0.16);
}

.tab-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.empty-panel {
  align-items: flex-start;
}

.empty-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.empty {
  margin: 0;
  color: var(--text-muted);
  line-height: 1.6;
}

.qa-scope-toggle {
  display: inline-flex;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.025);
}

.qa-scope-option {
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  padding: 9px 13px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.qa-scope-option.active {
  color: #ffffff;
  background: rgba(var(--accent-rgb), 0.18);
}

.qa-form {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
}

.qa-answer-box {
  padding: 18px;
  border: 1px solid rgba(var(--accent-rgb), 0.2);
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(var(--accent-rgb), 0.12), rgba(var(--accent-rgb), 0.07));
}

.qa-answer-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.qa-answer-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.qa-match-source {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--text-muted);
}

.qa-answer-head h3,
.qa-list-head h3 {
  margin: 0;
  font-size: 16px;
}

.qa-answer-body {
  font-size: 15px;
  line-height: 1.75;
  color: var(--text-primary);
}

.qa-answer-body :deep(h1),
.qa-answer-body :deep(h2),
.qa-answer-body :deep(h3),
.qa-answer-body :deep(h4) {
  margin: 16px 0 8px;
  font-weight: 700;
}

.qa-answer-body :deep(p) {
  margin: 0 0 10px;
}

.qa-answer-body :deep(ul),
.qa-answer-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.qa-answer-body :deep(li) {
  margin-bottom: 4px;
}

.qa-answer-body :deep(strong) {
  font-weight: 700;
}

.qa-answer-body :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 13px;
}

.qa-answer-body :deep(pre) {
  background: rgba(0, 0, 0, 0.3);
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}

.qa-answer-body :deep(pre code) {
  background: none;
  padding: 0;
}

.qa-answer-body :deep(blockquote) {
  border-left: 3px solid var(--border-strong);
  margin: 10px 0;
  padding-left: 14px;
  color: var(--text-secondary);
}

.qa-result-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.qa-item {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  display: flex;
  justify-content: space-between;
  gap: 16px;
  background: rgba(255, 255, 255, 0.025);
}

.qa-item-copy {
  min-width: 0;
}

.qa-item:hover {
  border-color: var(--border-strong);
}

.qa-labels {
  margin: 8px 0 0;
  color: var(--accent);
  font-size: 12px;
}

.qa-snippet {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.qa-actions {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.qa-pairs-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.qa-pairs-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.qa-pair-card {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.025);
}

.qa-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.qa-question,
.qa-answer {
  margin: 0;
  font-size: 14px;
  line-height: 1.65;
}

.qa-question strong,
.qa-answer strong {
  display: inline-flex;
  margin-right: 8px;
  color: var(--text-primary);
}

.qa-answer {
  color: var(--text-secondary);
  margin-top: 8px;
}

.raw-json {
  max-height: 60vh;
}

.highlighted-json {
  line-height: 1.6;
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

@media (max-width: 960px) {
  .result-layout {
    grid-template-columns: 1fr;
  }

  .catalog-panel {
    position: static;
    max-height: none;
  }
}

@media (max-width: 720px) {
  .qa-form {
    grid-template-columns: 1fr;
  }

  .qa-item {
    flex-direction: column;
  }

  .qa-actions,
  .qa-actions .ui-button {
    width: 100%;
  }
}
</style>

