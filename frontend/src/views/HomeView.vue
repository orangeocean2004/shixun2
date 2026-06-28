<script setup>
import { computed, ref } from 'vue'
import ConfigPanel from '../components/ConfigPanel.vue'
import MetricPanel from '../components/MetricPanel.vue'
import ChunkList from '../components/ChunkList.vue'
import { useChunkStore } from '../stores/chunkStore'

const { state, submitUpload } = useChunkStore()
const activeTab = ref('result')
const rawResultJson = computed(() => JSON.stringify(state.result, null, 2))

function handleSubmit(payload) {
  activeTab.value = 'result'
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
            :class="{ active: activeTab === 'json' }"
            @click="activeTab = 'json'"
          >
            原始 JSON
          </button>
        </div>
      </section>

      <template v-if="activeTab === 'result'">
        <MetricPanel :statistics="state.result.statistics" :strategy="state.result.strategy" />
        <ChunkList :chunks="state.result.chunks" />
      </template>

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
</style>
