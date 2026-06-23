import { apiFetch } from './client'

export async function uploadAndSegment({
  file,
  docId,
  minChars,
  targetChars,
  maxChars,
  overlapSentences,
}) {
  const form = new FormData()
  form.append('file', file)
  if (docId?.trim()) {
    form.append('doc_id', docId.trim())
  }
  form.append('min_chars', String(minChars))
  form.append('target_chars', String(targetChars))
  form.append('max_chars', String(maxChars))
  form.append('overlap_sentences', String(overlapSentences))

  return apiFetch('/api/segment/upload', {
    method: 'POST',
    body: form,
  })
}
