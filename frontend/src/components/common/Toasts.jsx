import { useApp } from '../../hooks/useApp'

export function Toasts() {
  const { toasts, dismiss } = useApp()

  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          className={`toast ${toast.type}`}
          onClick={() => dismiss(toast.id)}
        >
          {toast.message}
        </button>
      ))}
    </div>
  )
}
