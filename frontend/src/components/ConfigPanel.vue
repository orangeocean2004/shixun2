<script setup>
import { reactive, ref } from 'vue'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['submit'])

const file = ref(null)
const form = reactive({
  docId: '',
  minChars: 300,
  targetChars: 900,
  maxChars: 1200,
  overlapSentences: 1,
})

function onFileChange(event) {
  file.value = event.target.files?.[0] || null
}

function onSubmit() {
  if (!file.value) {
    return
  }

  emit('submit', {
    file: file.value,
    docId: form.docId,
    minChars: Number(form.minChars),
    targetChars: Number(form.targetChars),
    maxChars: Number(form.maxChars),
    overlapSentences: Number(form.overlapSentences),
  })
}
</script>

<template>
  <section class="panel">
    <h2>上传参数</h2>
    <div class="grid">
      <label>
        文档文件
        <input type="file" @change="onFileChange" :disabled="props.loading" />
      </label>
      <label>
        文档 ID（可选）
        <input v-model="form.docId" type="text" placeholder="默认使用文件名" :disabled="props.loading" />
      </label>
      <label>
        min_chars
        <input v-model.number="form.minChars" type="number" min="1" :disabled="props.loading" />
      </label>
      <label>
        target_chars
        <input v-model.number="form.targetChars" type="number" min="1" :disabled="props.loading" />
      </label>
      <label>
        max_chars
        <input v-model.number="form.maxChars" type="number" min="1" :disabled="props.loading" />
      </label>
      <label>
        overlap_sentences
        <input v-model.number="form.overlapSentences" type="number" min="0" :disabled="props.loading" />
      </label>
    </div>
    <button class="btn" :disabled="props.loading || !file" @click="onSubmit">
      {{ props.loading ? '处理中...' : '上传并分段' }}
    </button>
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

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 14px;
  color: var(--text-secondary);
}

input {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  background: var(--bg-surface-2);
  color: var(--text-primary);
}

input::placeholder {
  color: var(--text-muted);
}

input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px rgba(51, 199, 155, 0.2);
}

.btn {
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--accent);
  color: #0e1715;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 600;
}

.btn:hover:not(:disabled) {
  background: var(--accent-strong);
  transform: translateY(-1px);
}

.btn:active:not(:disabled) {
  transform: translateY(0) scale(0.985);
}

.btn:disabled {
  background: #5a6762;
  color: #b4beb9;
  cursor: not-allowed;
}
</style>
