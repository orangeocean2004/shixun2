export async function apiFetch(url, options = {}) {
  const response = await fetch(url, options)
  const body = await response.json().catch(() => ({}))

  if (!response.ok) {
    const message = body?.detail || `请求失败: ${response.status}`
    throw new Error(message)
  }

  return body
}
