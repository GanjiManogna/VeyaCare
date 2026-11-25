export const PAGES = Object.freeze({
  DASHBOARD: 'dashboard',
  DOCTORS: 'doctors',
  AVAILABILITY: 'availability',
  APPOINTMENTS: 'appointments',
  VOICE: 'voice',
  HISTORY: 'history',
  GUIDANCE: 'guidance',
})

export const PAGE_ROUTES = Object.freeze({
  [PAGES.DASHBOARD]: '/',
  [PAGES.DOCTORS]: '/doctors',
  [PAGES.AVAILABILITY]: '/availability',
  [PAGES.APPOINTMENTS]: '/my-appointments',
  [PAGES.VOICE]: '/voice-assistant',
  [PAGES.HISTORY]: '/call-history',
  [PAGES.GUIDANCE]: '/appointment-guidance',
})

export function pageFromLocation(pathname = window.location.pathname) {
  const normalized = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  return Object.entries(PAGE_ROUTES).find(([, path]) => path === normalized)?.[0] || PAGES.DASHBOARD
}

export function routeUrl(page, query = {}) {
  const base = PAGE_ROUTES[page] || PAGE_ROUTES[PAGES.DASHBOARD]
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value) !== '') params.set(key, String(value))
  })
  const search = params.toString()
  return search ? `${base}?${search}` : base
}
