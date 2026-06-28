<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  chunks: {
    type: Array,
    required: true,
  },
})

const collapsedIds = ref(new Set())
const chunkElements = new Map()

function isCollapsed(chunkId) {
  return collapsedIds.value.has(chunkId)
}

function toggleChunk(chunkId) {
  if (collapsedIds.value.has(chunkId)) {
    collapsedIds.value.delete(chunkId)
    return
  }
  collapsedIds.value.add(chunkId)
}

function collapseAll() {
  collapsedIds.value = new Set(props.chunks.map((chunk) => chunk.chunk_id))
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

function getChunkSummary(chunk) {
  if (typeof chunk.summary === 'string' && chunk.summary.trim()) {
    return chunk.summary.trim()
  }
  return ''
}

function setChunkRef(chunkId, el) {
  if (!el) {
    chunkElements.delete(chunkId)
    return
  }
  chunkElements.set(chunkId, el)
}

async function scrollToChunk(chunkId) {
  if (!chunkId) {
    return
  }
  collapsedIds.value.delete(chunkId)
  await nextTick()
  chunkElements.get(chunkId)?.scrollIntoView({
    behavior: 'smooth',
    block: 'start',
  })
}

defineExpose({
  scrollToChunk,
})

watch(
  () => props.chunks,
  () => {
    collapsedIds.value = new Set()
  },
)
</script>

<template>
  <section class="panel">
    <div class="panel-head">
      <h2>分段结果（{{ props.chunks.length }}）</h2>
      <button type="button" class="bulk-btn" @click="collapseAll">收起所有</button>
    </div>
    <article
      v-for="chunk in props.chunks"
      :key="chunk.chunk_id"
      :ref="(el) => setChunkRef(chunk.chunk_id, el)"
      class="chunk-card"
    >
      <div class="chunk-head">
        <div class="meta">
          <strong>{{ chunk.chunk_id }}</strong>
          <span>type: {{ chunk.chunk_type }}</span>
          <span>chars: {{ chunk.char_count }}</span>
        </div>
        <button type="button" class="toggle-btn" @click="toggleChunk(chunk.chunk_id)">
          {{ isCollapsed(chunk.chunk_id) ? '展开' : '收起' }}
        </button>
      </div>

      <Transition name="chunk-collapse">
        <div v-if="!isCollapsed(chunk.chunk_id)">
          <p v-if="chunk.title_path?.length" class="title-path">title_path: {{ chunk.title_path.join(' > ') }}</p>
          <p v-if="getChunkSummary(chunk)" class="summary">summary: {{ getChunkSummary(chunk) }}</p>
          <p v-if="getChunkLabels(chunk).length" class="labels">labels: {{ getChunkLabels(chunk).join(', ') }}</p>
          <pre class="content">{{ chunk.content }}</pre>
          <p v-if="chunk.quality_flags?.length" class="flags">
            quality_flags: {{ chunk.quality_flags.join(', ') }}
          </p>
        </div>
      </Transition>
    </article>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-surface);
  box-shadow: var(--shadow-soft);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-head h2 {
  margin: 0;
}

.bulk-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-surface-2);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 6px 10px;
  cursor: pointer;
}

.bulk-btn:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}

.chunk-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
  scroll-margin-top: 12px;
  background: var(--bg-surface-2);
}

.chunk-card:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.chunk-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 8px;
}

.meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.toggle-btn {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 4px 10px;
  cursor: pointer;
  flex-shrink: 0;
}

.toggle-btn:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}

.title-path {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}

.summary {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.labels {
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--accent);
}

.content {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 10px;
  color: var(--text-primary);
}

.flags {
  margin-top: 8px;
  font-size: 12px;
  color: var(--warning);
}

.chunk-collapse-enter-active,
.chunk-collapse-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}

.chunk-collapse-enter-from,
.chunk-collapse-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
