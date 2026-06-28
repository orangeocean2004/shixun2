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

      <div v-if="!isCollapsed(chunk.chunk_id)">
        <p v-if="chunk.title_path?.length" class="title-path">title_path: {{ chunk.title_path.join(' > ') }}</p>
        <pre class="content">{{ chunk.content }}</pre>
        <p v-if="chunk.quality_flags?.length" class="flags">
          quality_flags: {{ chunk.quality_flags.join(', ') }}
        </p>
      </div>
    </article>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
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
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 12px;
  padding: 6px 10px;
  cursor: pointer;
}

.chunk-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
  scroll-margin-top: 12px;
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
  color: #374151;
}

.toggle-btn {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 12px;
  padding: 4px 10px;
  cursor: pointer;
  flex-shrink: 0;
}

.title-path {
  margin: 0 0 8px;
  font-size: 13px;
  color: #4b5563;
}

.content {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 14px;
  background: #f9fafb;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  padding: 10px;
}

.flags {
  margin-top: 8px;
  font-size: 12px;
  color: #b45309;
}
</style>
