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

// 把 Markdown 表格文本转成 { headers, rows }
function parseMarkdownTable(text) {
  const lines = text.trim().split('\n')
  // 必须有至少两行非空，且包含 |
  const pipeLines = lines.filter(l => l.includes('|'))
  if (pipeLines.length < 2) return null

  // 第二行必须是分隔行 (如 | --- | --- |)
  const sep = pipeLines[1].replace(/\s/g, '')
  if (!/^\|[-:]+\|$/.test(sep)) return null

  const splitCells = (line) => line.split('|').slice(1, -1).map(c => c.trim())
  const header = splitCells(pipeLines[0])
  const rows = pipeLines.slice(2).map(splitCells).filter(r => r.length > 0)

  if (header.length === 0 || rows.length === 0) return null
  return { headers: header, rows }
}

function renderContentParts(content) {
  // 按表格分隔符切分：单独一行的 |---| 是 Markdown 表格标记
  const parts = []
  const tableSep = /\n\|[-:\s|]+\|\n/
  const segments = content.split(tableSep)

  if (segments.length === 1) {
    // 没有表格，只处理图片
    return _renderTextWithImages(content)
  }

  for (let i = 0; i < segments.length; i++) {
    if (i === 0) {
      // 第一个段：表格前的内容 + 表头行
      const lines = segments[i].split('\n')
      const lastPipe = lines.length - 1
      // 找到最后一个 | 行作为表头
      let headerIdx = -1
      for (let j = lines.length - 1; j >= 0; j--) {
        if (lines[j].includes('|')) { headerIdx = j; break }
      }
      if (headerIdx >= 0) {
        if (headerIdx > 0) {
          parts.push(..._renderTextWithImages(lines.slice(0, headerIdx).join('\n')))
        }
        // 表头行 + 分隔符 + 后续数据行组成表格
        const nextSeg = i + 1 < segments.length ? segments[i + 1] : ''
        const nextLines = nextSeg.split('\n')
        // 找到数据行的结束（下一个空行或文本开始处）
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
        // 数据行后面的文本
        if (dataEnd < nextLines.length) {
          parts.push(..._renderTextWithImages(nextLines.slice(dataEnd).join('\n')))
        }
        i++ // 跳过一个 segment
      } else {
        parts.push(..._renderTextWithImages(segments[i]))
      }
    } else if (i === segments.length - 1 || i % 2 === 0) {
      parts.push(..._renderTextWithImages(segments[i]))
    }
  }

  return parts.length ? parts : [{ type: 'text', value: content }]
}

// 处理纯文本中的图片引用
function _renderTextWithImages(text) {
  if (!text) return []
  const parts = []
  let lastIndex = 0
  let match
  IMAGE_PATTERN.lastIndex = 0

  while ((match = IMAGE_PATTERN.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const t = text.slice(lastIndex, match.index).trim()
      if (t) parts.push({ type: 'text', value: t })
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
    const t = text.slice(lastIndex).trim()
    if (t) parts.push({ type: 'text', value: t })
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
  border: 1px solid rgba(var(--accent-rgb), 0.42);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.32), rgba(var(--accent-rgb), 0.16));
  color: #eef5ff;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 10px;
  cursor: pointer;
  box-shadow: 0 8px 16px rgba(var(--accent-rgb), 0.18);
}

.bulk-btn:hover {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.48), rgba(var(--accent-rgb), 0.24));
  transform: translateY(-1px);
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
  border: 1px solid rgba(var(--accent-rgb), 0.38);
  border-radius: 8px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.26), rgba(var(--accent-rgb), 0.12));
  color: #e9f2ff;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 8px 14px rgba(var(--accent-rgb), 0.16);
}

.toggle-btn:hover {
  border-color: var(--accent);
  color: #ffffff;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.4), rgba(var(--accent-rgb), 0.2));
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
  border-radius: 8px;
  border: 1px solid var(--border);
  overflow: hidden;
}

.content-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 14px;
  background: rgba(255, 255, 255, 0.02);
  padding: 10px;
  color: var(--text-primary);
}

.content-image {
  margin: 0;
  padding: 10px;
  background: rgba(255, 255, 255, 0.04);
  border-top: 1px solid var(--border);
  text-align: center;
}

.content-image img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 6px;
}

.content-image figcaption {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 6px;
}

.content-table-wrap {
  overflow-x: auto;
  padding: 12px 10px;
  background: rgba(255, 255, 255, 0.015);
}

.content-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 13px;
  border: 1px solid rgba(var(--accent-rgb), 0.18);
  border-radius: 8px;
  overflow: hidden;
}

.content-table th {
  background: rgba(var(--accent-rgb), 0.12);
  color: #d0e0ff;
  font-weight: 600;
  padding: 10px 12px;
  text-align: left;
  font-size: 12px;
  letter-spacing: 0.3px;
  border-bottom: 2px solid rgba(var(--accent-rgb), 0.3);
}

.content-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: #c8d2e0;
}

.content-table tr:last-child td {
  border-bottom: none;
}

.content-table tbody tr:hover td {
  background: rgba(var(--accent-rgb), 0.06);
}

.content-table tbody tr:nth-child(even) td {
  background: rgba(255, 255, 255, 0.02);
}

.content-table tbody tr:nth-child(even):hover td {
  background: rgba(var(--accent-rgb), 0.06);
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
