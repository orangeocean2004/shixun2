export async function apiFetch(url, options = {}) {
  const controller = new AbortController()
  const timeout = options.timeout || 300_000 // default 5 min
  const timer = setTimeout(() => controller.abort(), timeout)
  const response = await fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer))
  const body = await response.json().catch(() => ({}))

  if (!response.ok) {
    const message = body?.detail || `请求失败: ${response.status}`
    throw new Error(message)
  }

  return body
}
