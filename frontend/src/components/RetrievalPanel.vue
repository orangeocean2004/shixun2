<script setup>
import { reactive } from 'vue'

const props = defineProps({
  docId: {
    type: String,
    required: true,
  },
  index: {
    type: Object,
    default: null,
  },
  result: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['query'])

const form = reactive({
  query: '',
  topK: 5,
})

function onSubmit() {
  if (!form.query.trim()) {
    return
  }
  emit('query', {
    query: form.query.trim(),
    topK: Number(form.topK),
  })
}

function pages(hit) {
  const values = new Set()
  for (const ref of hit.source_refs || []) {
    if (ref.page) {
      values.add(ref.page)
    }
  }
  return Array.from(values).join(', ')
}
</script>

<template>
  <section class="panel">
    <div class="head">
      <div>
        <h2>检索测试</h2>
        <p>doc_id: {{ props.docId }}</p>
      </div>
      <div v-if="props.index" class="index-info">
        <span>{{ props.index.embedding_backend }}</span>
        <strong>{{ props.index.chunk_count }} chunks</strong>
      </div>
    </div>

    <div class="query-row">
      <input
        v-model="form.query"
        type="text"
        placeholder="输入问题，例如：这个课题的验收指标是什么？"
        :disabled="props.loading"
        @keyup.enter="onSubmit"
      />
      <input v-model.number="form.topK" class="topk" type="number" min="1" max="20" :disabled="props.loading" />
      <button class="btn" :disabled="props.loading || !form.query.trim()" @click="onSubmit">
        {{ props.loading ? '检索中...' : '检索' }}
      </button>
    </div>

    <p v-if="props.error" class="error">{{ props.error }}</p>

    <div v-if="props.result" class="hits">
      <article v-for="hit in props.result.hits" :key="hit.chunk_id" class="hit">
        <div class="meta">
          <strong>{{ hit.chunk_id }}</strong>
          <span>score: {{ hit.score }}</span>
          <span>chars: {{ hit.char_count }}</span>
          <span v-if="pages(hit)">pages: {{ pages(hit) }}</span>
        </div>
        <p v-if="hit.title_path?.length" class="title-path">{{ hit.title_path.join(' > ') }}</p>
        <pre>{{ hit.content }}</pre>
      </article>
    </div>
  </section>
</template>

<style scoped>
.panel {
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  padding: 16px;
  background: #fff;
}

.head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

h2,
p {
  margin: 0;
}

.head p {
  margin-top: 6px;
  font-size: 13px;
  color: #6b7280;
}

.index-info {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  font-size: 13px;
  color: #4b5563;
}

.query-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 90px auto;
  gap: 10px;
  margin-bottom: 12px;
}

input {
  border: 1px solid #d1d5db;
  border-radius: 8px;
  padding: 9px;
}

.topk {
  text-align: center;
}

.btn {
  border: none;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  padding: 10px 14px;
  cursor: pointer;
}

.btn:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

.error {
  color: #dc2626;
  background: #fee2e2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  padding: 10px;
}

.hit {
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
  margin-top: 12px;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: #374151;
}

.title-path {
  margin: 8px 0;
  font-size: 13px;
  color: #4b5563;
}

pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  line-height: 1.5;
  font-size: 14px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px;
}

@media (max-width: 720px) {
  .head,
  .query-row {
    grid-template-columns: 1fr;
  }

  .head {
    display: block;
  }

  .index-info {
    align-items: flex-start;
    margin-top: 10px;
  }
}
</style>
