import { apiFetch } from './client'

export function getModelSettings() {
  return apiFetch('/api/settings/model')
}

export function updateModelSettings(payload) {
  return apiFetch('/api/settings/model', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}
