<script setup>
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
</script>

<template>
  <section class="panel">
    <h2>分段结果（{{ props.chunks.length }}）</h2>
    <article v-for="chunk in props.chunks" :key="chunk.chunk_id" class="chunk-card">
      <div class="meta">
        <strong>{{ chunk.chunk_id }}</strong>
        <span>type: {{ chunk.chunk_type }}</span>
        <span>chars: {{ chunk.char_count }}</span>
      </div>
      <p v-if="chunk.title_path?.length" class="title-path">title_path: {{ chunk.title_path.join(' > ') }}</p>
      <pre class="content">{{ chunk.content }}</pre>
      <p v-if="chunk.quality_flags?.length" class="flags">
        quality_flags: {{ chunk.quality_flags.join(', ') }}
      </p>
      <div v-if="chunk.tags?.length" class="tags">
        <span class="label">标签:</span>
        <span v-for="tag in chunk.tags" :key="tag" class="tag-chip">{{ tag }}</span>
      </div>
      <p v-if="chunk.summary" class="summary">
        <span class="label">摘要:</span> {{ chunk.summary }}
      </p>
      <div v-if="chunk.entity_labels?.length" class="entities">
        <span class="label">实体:</span>
        <span v-for="entity in chunk.entity_labels" :key="entity.value" class="entity-chip">{{ entity.type }}: {{ entity.value }}</span>
      </div>
      <div v-if="chunk.asset_refs?.length" class="assets">
        <span class="label">图片:</span>
        <div v-for="(ref, i) in chunk.asset_refs" :key="i" class="asset-image">
          <img
            v-if="ref.type === 'image'"
            :src="`/api/images/${docId}/${ref.filename}`"
            :alt="ref.alt || '图片'"
            loading="lazy"
          />
        </div>
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

.chunk-card {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 12px;
}

.meta {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #374151;
  margin-bottom: 8px;
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

.tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.tags .label,
.summary .label,
.entities .label,
.assets .label {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}

.tag-chip {
  display: inline-block;
  background: #dbeafe;
  color: #1e40af;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
}

.summary {
  margin-top: 6px;
  font-size: 13px;
  color: #374151;
  line-height: 1.5;
}

.entities {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.entity-chip {
  display: inline-block;
  background: #fef3c7;
  color: #92400e;
  padding: 2px 8px;
  border-radius: 8px;
  font-size: 11px;
}

.assets {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
}

.assets .label {
  flex-shrink: 0;
  line-height: 1.8;
}

.asset-image img {
  max-width: 100%;
  max-height: 400px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  display: block;
}
</style>
