export function Loader({ label = 'Loading…' }) {
  return (
    <div className="loader" role="status">
      <span className="loader-dot" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBanner({ message }) {
  if (!message) return null
  return <div className="banner error">{message}</div>
}

export function EmptyState({ title, body }) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  )
}
