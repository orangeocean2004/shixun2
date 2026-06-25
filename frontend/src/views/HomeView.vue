<script setup>
import ConfigPanel from '../components/ConfigPanel.vue'
import MetricPanel from '../components/MetricPanel.vue'
import ChunkList from '../components/ChunkList.vue'
import RetrievalPanel from '../components/RetrievalPanel.vue'
import { useChunkStore } from '../stores/chunkStore'

const { state, submitUpload, submitQuery } = useChunkStore()

function handleSubmit(payload) {
  submitUpload(payload)
}

function handleQuery(payload) {
  submitQuery(payload)
}
</script>

<template>
  <div class="layout">
    <ConfigPanel :loading="state.loading" @submit="handleSubmit" />

    <p v-if="state.loading" class="loading">正在处理文档，请稍候...</p>
    <p v-if="state.error" class="error">{{ state.error }}</p>

    <template v-if="state.result">
      <MetricPanel :statistics="state.result.statistics" :strategy="state.result.strategy" />
      <RetrievalPanel
        :doc-id="state.result.doc_id"
        :index="state.result.index"
        :result="state.queryResult"
        :loading="state.querying"
        :error="state.queryError"
        @query="handleQuery"
      />
      <ChunkList :chunks="state.result.chunks" :doc-id="state.result.doc_id" />
    </template>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
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
