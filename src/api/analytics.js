const API_URL = import.meta.env.VITE_API_URL || ''
export async function fetchAnalytics(signal) {
  if (!API_URL) return null
  const response = await fetch(`${API_URL}/analytics/overview`, { signal })
  if (!response.ok) throw new Error(`Analytics request failed (${response.status})`)
  return response.json()
}

export async function syncLiveData() {
  if (!API_URL) throw new Error('VITE_API_URL is not configured')
  const response = await fetch(`${API_URL}/api/sync-live-data`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`Live data sync failed (${response.status})`)
  return response.json()
}
