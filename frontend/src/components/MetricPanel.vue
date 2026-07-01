<script setup>
import { computed } from 'vue'

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

const metricItems = computed(() => {
  const statistics = props.statistics || {}
  return [
    { key: 'chunk_count', label: '分块数', value: formatValue(statistics.chunk_count) },
    { key: 'avg_chars', label: '平均字符数', value: formatValue(statistics.avg_chars) },
    { key: 'target_length_hit_rate', label: '目标长度命中率', value: formatPercent(statistics.target_length_hit_rate) },
    { key: 'oversized_count', label: '超长分块', value: formatValue(statistics.oversized_count) },
    { key: 'undersized_count', label: '过短分块', value: formatValue(statistics.undersized_count) },
    { key: 'source_ref_complete_rate', label: '来源引用完整率', value: formatPercent(statistics.source_ref_complete_rate) },
  ]
})

function formatValue(value) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Number.isInteger(value) ? String(value) : value.toFixed(2)
  }
  if (value === null || value === undefined || value === '') {
    return '--'
  }
  return String(value)
}

function formatPercent(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return formatValue(value)
  }

  const normalized = value <= 1 ? value * 100 : value
  return `${normalized.toFixed(normalized % 1 === 0 ? 0 : 1)}%`
}
</script>

<template>
  <section class="panel metric-panel">
    <div class="metric-header">
      <div>
        <h2 class="panel-title">统计信息</h2>
        <p class="panel-subtitle">快速判断当前分段策略是否稳定、是否接近期望长度。</p>
      </div>
    </div>

    <div class="metrics-grid">
      <div v-for="item in metricItems" :key="item.key" class="metric-card">
        <span class="metric-label">{{ item.label }}</span>
        <strong class="metric-value">{{ item.value }}</strong>
      </div>
    </div>

    <div class="strategy-block">
      <div class="strategy-head">
        <h3>分段策略</h3>
        <span class="ui-pill">运行参数快照</span>
      </div>
      <pre class="ui-code strategy-code">{{ JSON.stringify(props.strategy, null, 2) }}</pre>
    </div>
  </section>
</template>

<style scoped>
.metric-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 12px;
}

.metric-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 98px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.015));
}

.metric-card:hover {
  border-color: var(--border-strong);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.042), rgba(255, 255, 255, 0.02));
}

.metric-label {
  color: var(--text-muted);
  font-size: 12px;
  letter-spacing: 0.02em;
}

.metric-value {
  color: var(--text-primary);
  font-size: 24px;
  line-height: 1.1;
}

.strategy-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.strategy-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.strategy-head h3 {
  margin: 0;
  font-size: 15px;
}

.strategy-code {
  max-height: 260px;
  font-size: 13px;
  line-height: 1.6;
}
</style>
