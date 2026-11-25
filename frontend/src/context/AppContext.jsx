import { useCallback, useEffect, useMemo, useState } from 'react'
import { AppContext } from './app-context'
import { pageFromLocation, PAGES, routeUrl } from '../routes'

const DISPLAY_NAME_KEY = 'veyacare:display-name'
const SIDEBAR_COLLAPSED_KEY = 'veyacare:sidebar-collapsed'

function readDisplayName() {
  try { return window.localStorage.getItem(DISPLAY_NAME_KEY)?.trim() || '' } catch { return '' }
}

function readSidebarCollapsed() {
  try { return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === 'true' } catch { return false }
}

export function AppProvider({ children }) {
  const [page, setPageState] = useState(() => pageFromLocation())
  const [toasts, setToasts] = useState([])
  const [displayName, setDisplayNameState] = useState(readDisplayName)
  const [sidebarCollapsed, setSidebarCollapsedState] = useState(readSidebarCollapsed)

  const setDisplayName = useCallback((value) => {
    const normalized = value.trim()
    setDisplayNameState(normalized)
    try { window.localStorage.setItem(DISPLAY_NAME_KEY, normalized) } catch { /* storage can be disabled */ }
  }, [])

  const setSidebarCollapsed = useCallback((value) => {
    setSidebarCollapsedState(value)
    try { window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(value)) } catch { /* storage can be disabled */ }
  }, [])

  const setPage = useCallback((nextPage, { query = {}, replace = false } = {}) => {
    const validPage = Object.hasOwn(PAGES, String(nextPage).toUpperCase()) ? nextPage : PAGES.DASHBOARD
    const url = routeUrl(validPage, query)
    if (window.location.pathname + window.location.search !== url) {
      const method = replace ? 'replaceState' : 'pushState'
      window.history[method]({ veyacarePage: validPage }, '', url)
    }
    setPageState(validPage)
    window.dispatchEvent(new Event('veyacare:navigate'))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  useEffect(() => {
    function restoreRoute() {
      const restoredPage = pageFromLocation()
      const knownRoute = routeUrl(restoredPage)
      if (restoredPage === PAGES.DASHBOARD && window.location.pathname !== knownRoute) {
        window.history.replaceState({ veyacarePage: restoredPage }, '', knownRoute)
      }
      setPageState(restoredPage)
    }
    restoreRoute()
    window.addEventListener('popstate', restoreRoute)
    return () => window.removeEventListener('popstate', restoreRoute)
  }, [])

  const notify = useCallback((message, type = 'success') => {
    const id = crypto.randomUUID()
    setToasts((current) => [...current, { id, message, type }])
    window.setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, 4200)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const value = useMemo(
    () => ({ page, setPage, toasts, notify, dismiss, displayName, setDisplayName, sidebarCollapsed, setSidebarCollapsed }),
    [page, setPage, toasts, notify, dismiss, displayName, setDisplayName, sidebarCollapsed, setSidebarCollapsed],
  )

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
