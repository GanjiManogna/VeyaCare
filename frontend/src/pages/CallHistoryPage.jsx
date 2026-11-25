import { useEffect, useState } from 'react'
import { EmptyState } from '../components/common/Loader'
import {
  CALL_HISTORY_EVENT,
  formatDuration,
  getCallHistory,
} from '../utils/callHistory'

export function CallHistoryPage() {
  const [rows, setRows] = useState(() => getCallHistory())

  useEffect(() => {
    const refresh = () => setRows(getCallHistory())
    window.addEventListener(CALL_HISTORY_EVENT, refresh)
    window.addEventListener('storage', refresh)
    return () => {
      window.removeEventListener(CALL_HISTORY_EVENT, refresh)
      window.removeEventListener('storage', refresh)
    }
  }, [])

  return (
    <div className="page-stack">
      <section className="page-intro">
        <div>
          <p className="eyebrow">Sessions</p>
          <h1>Call history</h1>
          <p className="lede">
            These notes stay in this browser after you start or end a call.
            The clinic service does not store a call log.
          </p>
        </div>
      </section>
      {rows.length === 0 ? (
        <EmptyState
          title="No calls yet"
          body="Start a conversation with the receptionist from the dashboard."
        />
      ) : (
        <div className="log-list">
          {rows.map((row) => (
            <article key={row.id} className="log-row">
              <div>
                <strong>{new Date(row.startedAt).toLocaleString()}</strong>
                <p className="muted">{row.note}</p>
              </div>
              <div className="visit-actions">
                <span>{formatDuration(row.durationSeconds || 0)}</span>
                <span className={`chip ${row.status}`}>{row.status}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
