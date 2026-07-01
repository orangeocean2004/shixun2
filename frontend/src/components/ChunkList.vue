<script setup>
import { nextTick, ref, watch } from 'vue'

const props = defineProps({
  chunks: {
    type: Array,
    required: true,
  },
  docId: {
    type: String,
    default: '',
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

const IMAGE_PATTERN = /\[IMAGE:\s*([^\]]+)\]/g

function getDocId() {
  return props.docId || ''
}

function parseMarkdownTable(text) {
  const lines = text.trim().split('\n')
  const pipeLines = lines.filter(l => l.includes('|'))
  if (pipeLines.length < 2) return null

  const sep = pipeLines[1].replace(/\s/g, '')
  if (!/^\|[-:]+\|$/.test(sep)) return null

  const splitCells = (line) => line.split('|').slice(1, -1).map(c => c.trim())
  const header = splitCells(pipeLines[0])
  const rows = pipeLines.slice(2).map(splitCells).filter(r => r.length > 0)

  if (header.length === 0 || rows.length === 0) return null
  return { headers: header, rows }
}

function renderContentParts(content) {
  const parts = []
  const tableSep = /\n\|[-:\s|]+\|\n/
  const segments = content.split(tableSep)

  if (segments.length === 1) {
    return renderTextWithImages(content)
  }

  for (let i = 0; i < segments.length; i++) {
    if (i === 0) {
      const lines = segments[i].split('\n')
      let headerIdx = -1
      for (let j = lines.length - 1; j >= 0; j--) {
        if (lines[j].includes('|')) {
          headerIdx = j
          break
        }
      }
      if (headerIdx >= 0) {
        if (headerIdx > 0) {
          parts.push(...renderTextWithImages(lines.slice(0, headerIdx).join('\n')))
        }
        const nextSeg = i + 1 < segments.length ? segments[i + 1] : ''
        const nextLines = nextSeg.split('\n')
        let dataEnd = 0
        for (let j = 0; j < nextLines.length; j++) {
          if (nextLines[j].includes('|')) dataEnd = j + 1
          else if (dataEnd > 0) break
        }
        const tableLines = [lines[headerIdx], '| --- |', ...nextLines.slice(0, dataEnd)]
        const tableText = tableLines.join('\n')
        const tableData = parseMarkdownTable(tableText)
        if (tableData) {
          parts.push({ type: 'table', ...tableData })
        } else {
          parts.push({ type: 'text', value: tableText })
        }
        if (dataEnd < nextLines.length) {
          parts.push(...renderTextWithImages(nextLines.slice(dataEnd).join('\n')))
        }
        i++
      } else {
        parts.push(...renderTextWithImages(segments[i]))
      }
    } else if (i === segments.length - 1 || i % 2 === 0) {
      parts.push(...renderTextWithImages(segments[i]))
    }
  }

  return parts.length ? parts : [{ type: 'text', value: content }]
}

function renderTextWithImages(text) {
  if (!text) return []
  const parts = []
  let lastIndex = 0
  let match
  IMAGE_PATTERN.lastIndex = 0

  while ((match = IMAGE_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const value = text.slice(lastIndex, match.index).trim()
      if (value) parts.push({ type: 'text', value })
    }
    const filename = match[1]
    const docId = getDocId()
    parts.push({
      type: 'image',
      filename,
      url: docId ? `/api/images/${encodeURIComponent(docId)}/${filename}` : '',
    })
    lastIndex = match.index + match[0].length
  }
  if (lastIndex < text.length) {
    const value = text.slice(lastIndex).trim()
    if (value) parts.push({ type: 'text', value })
  }
  return parts
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

function getMetaItems(chunk) {
  return [
    { label: '类型', value: chunk.chunk_type || '--' },
    { label: '字符数', value: chunk.char_count ?? '--' },
  ]
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
  <section class="panel chunk-panel">
    <div class="panel-head">
      <div>
        <h2 class="panel-title">分段结果（{{ props.chunks.length }}）</h2>
        <p class="panel-subtitle">逐段查看摘要、标签、正文和质量提示，方便快速比对分段效果。</p>
      </div>
      <button type="button" class="ui-button ui-button--secondary" @click="collapseAll">收起所有</button>
    </div>

    <article
      v-for="chunk in props.chunks"
      :key="chunk.chunk_id"
      :ref="(el) => setChunkRef(chunk.chunk_id, el)"
      class="chunk-card"
    >
      <div class="chunk-head">
        <div class="chunk-main-meta">
          <strong class="chunk-id">{{ chunk.chunk_id }}</strong>
          <div class="chunk-pills">
            <span v-for="item in getMetaItems(chunk)" :key="item.label" class="ui-pill">
              <span class="pill-label">{{ item.label }}</span>
              <span class="pill-value">{{ item.value }}</span>
            </span>
          </div>
        </div>
        <button type="button" class="ui-button ui-button--ghost chunk-toggle" @click="toggleChunk(chunk.chunk_id)">
          {{ isCollapsed(chunk.chunk_id) ? '展开内容' : '收起内容' }}
        </button>
      </div>

      <Transition name="chunk-collapse">
        <div v-if="!isCollapsed(chunk.chunk_id)" class="chunk-body">
          <p v-if="chunk.title_path?.length" class="chunk-inline-meta">
            <span class="chunk-inline-label">标题路径</span>
            <span>{{ chunk.title_path.join(' > ') }}</span>
          </p>
          <p v-if="getChunkSummary(chunk)" class="chunk-summary">
            <span class="chunk-inline-label">摘要</span>
            <span>{{ getChunkSummary(chunk) }}</span>
          </p>
          <p v-if="getChunkLabels(chunk).length" class="chunk-inline-meta">
            <span class="chunk-inline-label">标签</span>
            <span>{{ getChunkLabels(chunk).join('、') }}</span>
          </p>

          <div class="content">
            <template v-for="(part, pi) in renderContentParts(chunk.content)" :key="pi">
              <pre v-if="part.type === 'text'" class="content-text">{{ part.value }}</pre>
              <figure v-else-if="part.type === 'image'" class="content-image">
                <img :src="part.url" :alt="part.filename" loading="lazy" />
                <figcaption>{{ part.filename }}</figcaption>
              </figure>
              <div v-else-if="part.type === 'table'" class="content-table-wrap">
                <table class="content-table">
                  <thead>
                    <tr>
                      <th v-for="(h, hi) in part.headers" :key="hi">{{ h }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in part.rows" :key="ri">
                      <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>
          </div>

          <p v-if="chunk.quality_flags?.length" class="chunk-inline-meta chunk-inline-meta--warning">
            <span class="chunk-inline-label">质量提示</span>
            <span>{{ chunk.quality_flags.join('、') }}</span>
          </p>
        </div>
      </Transition>
    </article>
  </section>
</template>

<style scoped>
.chunk-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}

.chunk-card {
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 14px;
  scroll-margin-top: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.012));
}

.chunk-card:hover {
  border-color: var(--border-strong);
}

.chunk-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
}

.chunk-main-meta {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.chunk-id {
  font-size: 15px;
  line-height: 1.4;
}

.chunk-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pill-label {
  color: var(--text-muted);
}

.pill-value {
  color: var(--text-primary);
}

.chunk-toggle {
  flex-shrink: 0;
}

.chunk-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 14px;
}

.chunk-inline-meta,
.chunk-summary {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
}

.chunk-inline-meta--warning {
  color: var(--warning);
}

.chunk-inline-label {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.content {
  border-radius: 16px;
  border: 1px solid var(--border);
  overflow: hidden;
  background: rgba(255, 255, 255, 0.015);
}

.content-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.65;
  font-size: 14px;
  background: transparent;
  padding: 14px;
  color: var(--text-primary);
}

.content-image {
  margin: 0;
  padding: 14px;
  background: rgba(255, 255, 255, 0.02);
  border-top: 1px solid var(--border);
  text-align: center;
}

.content-image img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 8px;
}

.content-image figcaption {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 8px;
}

.content-table-wrap {
  overflow-x: auto;
  padding: 14px;
  background: rgba(255, 255, 255, 0.012);
}

.content-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  border: 1px solid rgba(var(--accent-rgb), 0.14);
  border-radius: 12px;
  overflow: hidden;
}

.content-table th {
  background: rgba(var(--accent-rgb), 0.08);
  color: var(--text-primary);
  font-weight: 600;
  padding: 10px 12px;
  text-align: left;
  font-size: 12px;
  border-bottom: 1px solid rgba(var(--accent-rgb), 0.18);
}

.content-table td {
  padding: 9px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.01);
}

.content-table tr:last-child td {
  border-bottom: none;
}

.content-table tbody tr:nth-child(even) td {
  background: rgba(255, 255, 255, 0.02);
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

@media (max-width: 720px) {
  .chunk-head {
    flex-direction: column;
  }

  .chunk-toggle {
    width: 100%;
  }
}
</style>
