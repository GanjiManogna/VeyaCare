const STORAGE_KEY = 'veyacare.callHistory'
// Read old browser-only records so the VeyaCare rename does not discard history.
const LEGACY_KEY = 'nexovai.callHistory'
export const CALL_HISTORY_EVENT = 'veyacare-call-history'

function readHistory(key) {
  try {
    const raw = localStorage.getItem(key)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export function getCallHistory() {
  const current = readHistory(STORAGE_KEY)
  const legacy = readHistory(LEGACY_KEY)
  const seen = new Set(current.map((row) => row.id))
  return [...current, ...legacy.filter((row) => !seen.has(row.id))].slice(0, 50)
}

export function addCallRecord(record) {
  const history = getCallHistory().filter((row) => row.id !== record.id)
  const next = [
    {
      id: crypto.randomUUID(),
      startedAt: new Date().toISOString(),
      ...record,
    },
    ...history,
  ].slice(0, 50)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  window.dispatchEvent(new Event(CALL_HISTORY_EVENT))
  return next
}

export function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
