import { reactive } from 'vue'
import { queryIndexedDocument, uploadSegmentAndIndex } from '../api/chunking'

const state = reactive({
  loading: false,
  querying: false,
  error: '',
  queryError: '',
  result: null,
  queryResult: null,
})

export function useChunkStore() {
  async function submitUpload(payload) {
    state.loading = true
    state.error = ''
    state.queryError = ''
    state.queryResult = null
    try {
      state.result = await uploadSegmentAndIndex(payload)
    } catch (error) {
      state.error = error instanceof Error ? error.message : '上传失败'
      state.result = null
    } finally {
      state.loading = false
    }
  }

  async function submitQuery(payload) {
    if (!state.result?.doc_id) {
      state.queryError = '请先上传并入库文档'
      return
    }

    state.querying = true
    state.queryError = ''
    try {
      state.queryResult = await queryIndexedDocument({
        docId: state.result.doc_id,
        query: payload.query,
        topK: payload.topK,
      })
    } catch (error) {
      state.queryError = error instanceof Error ? error.message : '检索失败'
      state.queryResult = null
    } finally {
      state.querying = false
    }
  }

  return {
    state,
    submitUpload,
    submitQuery,
  }
}
