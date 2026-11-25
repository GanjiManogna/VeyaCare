import { useState } from 'react'
import { useApp } from '../../hooks/useApp'
import { PAGES } from '../../routes'

const LINKS = [
  { id: PAGES.DASHBOARD, label: 'Dashboard', icon: DashboardIcon },
  { id: PAGES.DOCTORS, label: 'Find Doctors', icon: DoctorsIcon },
  { id: PAGES.AVAILABILITY, label: 'View Availability', icon: CalendarIcon },
  { id: PAGES.APPOINTMENTS, label: 'My Appointments', icon: CalendarIcon },
  { id: PAGES.VOICE, label: 'Voice Assistant', icon: VoiceIcon },
  { id: PAGES.GUIDANCE, label: 'Appointment Guidance', icon: GuidanceIcon },
  { id: PAGES.HISTORY, label: 'Call History', icon: HistoryIcon },
]

export function Sidebar() {
  const { page, setPage, sidebarCollapsed, setSidebarCollapsed, displayName } = useApp()
  const [mobileOpen, setMobileOpen] = useState(false)

  function renderLinks(links, mobile = false) {
    return links.map((link) => (
      <button
        key={link.id}
        className={page === link.id ? 'active' : ''}
        aria-current={page === link.id ? 'page' : undefined}
        aria-label={sidebarCollapsed && !mobile ? link.label : undefined}
        title={sidebarCollapsed && !mobile ? link.label : undefined}
        onClick={() => { setPage(link.id); setMobileOpen(false) }}
      >
        <link.icon />
        <span className="nav-label">{link.label}</span>
      </button>
    ))
  }

  return (
    <>
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            V
          </span>
          <div className="brand-copy">
            <strong>VeyaCare</strong>
            <p>Your care, in good hands.</p>
          </div>
        </div>
        <button className="sidebar-toggle" onClick={() => setSidebarCollapsed(!sidebarCollapsed)} aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
          <ChevronIcon collapsed={sidebarCollapsed} />
        </button>
        <nav aria-label="Primary">
          <p className="nav-group-label">Main</p>{renderLinks(LINKS.slice(0, 4))}
          <p className="nav-group-label assistance-label">Assistance</p>{renderLinks(LINKS.slice(4))}
        </nav>
        <div className="sidebar-profile" title={sidebarCollapsed ? displayName : undefined}>
          <span className="profile-avatar" aria-hidden="true">{displayName.slice(0, 1).toUpperCase()}</span>
          <span className="sidebar-profile-name">{displayName}</span>
        </div>
        <p className="sidebar-footnote">A quieter way to book care.</p>
      </aside>
      <button className="mobile-menu-toggle" onClick={() => setMobileOpen(true)} aria-label="Open navigation" aria-expanded={mobileOpen}>
        <MenuIcon />
      </button>
      {mobileOpen ? (
        <div className="mobile-drawer-backdrop" role="presentation" onClick={() => setMobileOpen(false)}>
          <aside className="sidebar mobile-drawer" role="dialog" aria-modal="true" aria-label="Primary navigation" onClick={(event) => event.stopPropagation()}>
            <div className="brand"><span className="brand-mark" aria-hidden="true">V</span><div><strong>VeyaCare</strong><p>Your care, in good hands.</p></div></div>
            <button className="drawer-close" onClick={() => setMobileOpen(false)} aria-label="Close navigation">×</button>
            <nav aria-label="Primary mobile">
              <p className="nav-group-label">Main</p>{renderLinks(LINKS.slice(0, 4), true)}
              <p className="nav-group-label assistance-label">Assistance</p>{renderLinks(LINKS.slice(4), true)}
            </nav>
          </aside>
        </div>
      ) : null}
    </>
  )
}

function VoiceIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3m-4 0h8"/></svg>
}

function GuidanceIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M9.8 9a2.3 2.3 0 1 1 3.8 1.8c-1 .8-1.6 1.2-1.6 2.7M12 17h.01"/></svg>
}

function DashboardIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 4h7v7H4V4zm9 0h7v4h-7V4zM4 13h7v7H4v-7zm9 3h7v4h-7v-4z" />
    </svg>
  )
}

function DoctorsIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8" r="3" />
      <path d="M6 19c1.2-3 3.4-4.5 6-4.5S16.8 16 18 19" />
    </svg>
  )
}

function CalendarIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2" />
      <path d="M8 3v4M16 3v4M4 10h16" />
    </svg>
  )
}

function HistoryIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 7v6l4 2" />
      <circle cx="12" cy="12" r="8" />
    </svg>
  )
}

function ChevronIcon({ collapsed }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d={collapsed ? 'm9 5 7 7-7 7' : 'm15 5-7 7 7 7'} /></svg>
}

function MenuIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
}
