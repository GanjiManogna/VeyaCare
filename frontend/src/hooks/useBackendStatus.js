import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

export function useBackendStatus() {
  const [status, setStatus] = useState({
    connected: false,
    loading: true,
    message: 'Checking backend…',
  })

  useEffect(() => {
    let cancelled = false

    async function check() {
      try {
        const data = await getHealth()
        if (!cancelled) {
          setStatus({
            connected: data.status === 'healthy',
            loading: false,
            message: data.service || 'Backend connected',
          })
        }
      } catch {
        if (!cancelled) {
          setStatus({
            connected: false,
            loading: false,
            message: 'Backend unreachable',
          })
        }
      }
    }

    check()
    const timer = window.setInterval(check, 15000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  return status
}
