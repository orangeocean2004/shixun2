import { reactive } from 'vue'
import { uploadAndSegment } from '../api/chunking'

const state = reactive({
  loading: false,
  error: '',
  result: null,
})

export function useChunkStore() {
  async function submitUpload(payload) {
    state.loading = true
    state.error = ''
    try {
      state.result = await uploadAndSegment(payload)
    } catch (error) {
      state.error = error instanceof Error ? error.message : '上传失败'
      state.result = null
    } finally {
      state.loading = false
    }
  }

  return {
    state,
    submitUpload,
  }
}
