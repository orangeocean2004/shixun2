<script setup>
const props = defineProps({
  statistics: {
    type: Object,
    required: true,
  },
  strategy: {
    type: Object,
    required: true,
  },
})
</script>

<template>
  <section class="panel">
    <h2>统计信息</h2>
    <div class="metrics">
      <div class="metric-item"><span>chunk_count</span><strong>{{ props.statistics.chunk_count }}</strong></div>
      <div class="metric-item"><span>avg_chars</span><strong>{{ props.statistics.avg_chars }}</strong></div>
      <div class="metric-item"><span>target_hit_rate</span><strong>{{ props.statistics.target_length_hit_rate }}</strong></div>
      <div class="metric-item"><span>oversized</span><strong>{{ props.statistics.oversized_count }}</strong></div>
      <div class="metric-item"><span>undersized</span><strong>{{ props.statistics.undersized_count }}</strong></div>
      <div class="metric-item"><span>source_ref_rate</span><strong>{{ props.statistics.source_ref_complete_rate }}</strong></div>
    </div>

    <h3>分段策略</h3>
    <pre>{{ JSON.stringify(props.strategy, null, 2) }}</pre>
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

.metrics {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.metric-item {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  background: var(--bg-surface-2);
}

.metric-item:hover {
  border-color: var(--border-strong);
  transform: translateY(-1px);
}

.metric-item span {
  font-size: 12px;
  color: var(--text-muted);
}

.metric-item strong {
  color: var(--text-primary);
}

pre {
  background: var(--bg-code);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  overflow-x: auto;
  color: var(--text-secondary);
}
</style>
