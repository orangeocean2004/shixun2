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
      if (error instanceof Error && error.name === 'AbortError') {
        state.error = '请求超时，请确认后端服务是否已启动'
      } else if (error instanceof TypeError && error.message === 'Failed to fetch') {
        state.error = '无法连接后端服务，请确认后端已启动（http://localhost:8000）'
      } else {
        state.error = error instanceof Error ? error.message : '上传失败'
      }
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

