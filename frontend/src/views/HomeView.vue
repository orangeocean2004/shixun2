<script setup>
import { computed, ref } from 'vue'
import ConfigPanel from '../components/ConfigPanel.vue'
import MetricPanel from '../components/MetricPanel.vue'
import ChunkList from '../components/ChunkList.vue'
import { queryRetrievedChunks } from '../api/chunking'
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
const rawResultJson = computed(() => JSON.stringify(state.result, null, 2))

function getCatalogLabel(chunk) {
  const lastTitle = chunk.title_path?.at(-1)
  return lastTitle || chunk.chunk_id
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

  const docId = qaDocId.value.trim() || state.result?.doc_id
  const question = qaQuestion.value.trim()
  if (!docId) {
    qaError.value = '请先上传文档或填写 doc_id。'
    return
  }
  if (!question) {
    qaError.value = '请输入问题。'
    return
  }

  qaLoading.value = true
  try {
    const response = await queryRetrievedChunks({
      docId,
      question,
    })
    qaDocId.value = response.doc_id || docId
    qaRetrievedChunks.value = response.chunks || []
  } catch (error) {
    qaError.value = error?.message || '检索失败，请稍后重试。'
  } finally {
    qaLoading.value = false
  }
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
    <ConfigPanel :loading="state.loading" @submit="handleSubmit" />

    <p v-if="state.loading" class="loading">正在处理文档，请稍候...</p>
    <p v-if="state.error" class="error">{{ state.error }}</p>

    <template v-if="state.result">
      <section class="panel tabs-panel">
        <div class="tabs">
          <button
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'result' }"
            @click="activeTab = 'result'"
          >
            分段结果
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'qa' }"
            @click="activeTab = 'qa'"
          >
            问答检索
          </button>
          <button
            type="button"
            class="tab-btn"
            :class="{ active: activeTab === 'json' }"
            @click="activeTab = 'json'"
          >
            原始 JSON
          </button>
        </div>
      </section>

      <section v-if="activeTab === 'result'" class="result-layout">
        <aside class="panel catalog-panel">
          <h2>目录</h2>
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
          <ChunkList ref="resultChunkListRef" :chunks="state.result.chunks" />
        </div>
      </section>

      <section v-else-if="activeTab === 'qa'" class="panel qa-panel">
        <h2>问答检索</h2>
        <div class="qa-form">
          <input v-model="qaDocId" type="text" placeholder="doc_id（可选，默认使用上传结果）" />
          <input v-model="qaQuestion" type="text" placeholder="输入问题，例如：这份文档的核心结论是什么？" />
          <button type="button" class="tab-btn" :disabled="qaLoading" @click="runQuery">
            {{ qaLoading ? '检索中...' : '提交问题' }}
          </button>
        </div>

        <p v-if="qaError" class="error inline-error">{{ qaError }}</p>

        <div v-if="qaRetrievedChunks.length" class="qa-result-list">
          <h3>已检索 chunks（{{ qaRetrievedChunks.length }}）</h3>
          <article v-for="chunk in qaRetrievedChunks" :key="chunk.chunk_id" class="qa-item">
            <div>
              <strong>{{ chunk.chunk_id }}</strong>
              <p class="qa-snippet">{{ chunk.summary || chunk.content || '无摘要' }}</p>
            </div>
            <div class="qa-actions">
              <button type="button" class="tab-btn" @click="jumpToChunk(chunk.chunk_id, 'qa')">定位</button>
              <button type="button" class="tab-btn" @click="openAllChunksView(chunk)">view more</button>
            </div>
          </article>

          <h3>详细信息</h3>
          <ChunkList ref="qaChunkListRef" :chunks="qaRetrievedChunks" />
        </div>

        <p v-else-if="!qaLoading" class="empty">暂无检索结果</p>
      </section>

      <section v-else class="panel">
        <h2>原始 JSON 返回值</h2>
        <pre class="raw-json">{{ rawResultJson }}</pre>
      </section>
    </template>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
}

.tabs-panel {
  padding: 10px;
}

.tabs {
  display: flex;
  gap: 8px;
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

.catalog-panel h2 {
  margin: 0 0 10px;
}

.catalog-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.catalog-item {
  width: 100%;
  text-align: left;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 13px;
  padding: 8px 10px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.catalog-item.active {
  border-color: #2563eb;
  color: #1d4ed8;
  background: #eff6ff;
}

.result-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tab-btn {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  padding: 8px 12px;
  font-size: 14px;
  color: #374151;
  cursor: pointer;
}

.tab-btn.active {
  border-color: #2563eb;
  color: #1d4ed8;
  background: #eff6ff;
}

.qa-panel h2 {
  margin-top: 0;
}

.qa-form {
  display: grid;
  grid-template-columns: 1fr 2fr auto;
  gap: 8px;
  margin-bottom: 12px;
}

.qa-form input {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 14px;
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
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.qa-snippet {
  margin: 6px 0 0;
  color: #4b5563;
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
  color: #6b7280;
}

.raw-json {
  margin: 0;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
  overflow: auto;
  max-height: 60vh;
}

.loading {
  margin: 0;
  color: #1d4ed8;
}

.error {
  margin: 0;
  color: #dc2626;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 10px;
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
}
</style>
