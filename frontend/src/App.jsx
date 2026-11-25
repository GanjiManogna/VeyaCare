import { useState } from 'react'
import { AppProvider } from './context/AppContext'
import { useApp } from './hooks/useApp'
import { useClinicData } from './hooks/useClinicData'
import { useVoiceCall } from './hooks/useVoiceCall'
import { Sidebar } from './components/layout/Sidebar'
import { Header } from './components/layout/Header'
import { Toasts } from './components/common/Toasts'
import { CancelModal } from './components/appointments/CancelModal'
import { DashboardPage } from './pages/DashboardPage'
import { DoctorsPage } from './pages/DoctorsPage'
import { AppointmentsPage } from './pages/AppointmentsPage'
import { AvailabilityPage } from './pages/AvailabilityPage'
import { CallHistoryPage } from './pages/CallHistoryPage'
import { VoiceAssistantPage } from './pages/VoiceAssistantPage'
import { AppointmentGuidancePage } from './pages/AppointmentGuidancePage'
import { bookAppointment, cancelAppointment } from './api/client'
import { PAGES } from './routes'
import './App.css'

function ClinicApp() {
  const { page, notify, displayName, setDisplayName, sidebarCollapsed } = useApp()
  const clinic = useClinicData()
  const voice = useVoiceCall(displayName, clinic.rememberPatientPhone, clinic.refresh)
  const [booking, setBooking] = useState(false)
  const [cancellingId, setCancellingId] = useState(null)
  const [cancelTarget, setCancelTarget] = useState(null)

  async function handleBook(payload) {
    setBooking(true)
    try {
      const result = await bookAppointment({
        ...payload,
        phone_number: payload.phone_number,
        patient_name: payload.patient_name?.trim() || null,
        booked_by_name: payload.booked_by_name?.trim() || null,
      })
      notify(`Appointment booked for ${result.patient_name || payload.patient_name} with ${result.doctor} on ${result.date} at ${result.time}. Reference ${result.appointment_reference}. Check-in code ${result.checkin_code}.`)
      clinic.rememberPatientPhone(payload.phone_number)
      clinic.refresh()
      return result
    } catch (err) {
      notify(err.message, 'error')
      return false
    } finally {
      setBooking(false)
    }
  }

  async function handleCancel(payload) {
    if (cancellingId !== null) return
    setCancellingId(payload.appointment_id)
    try {
      const result = await cancelAppointment({
        ...payload,
        phone_number: payload.phone_number,
      })
      notify(result.message || 'Appointment cancelled successfully.')
      clinic.updateAppointmentStatus(payload.appointment_id, 'cancelled')
      setCancelTarget(null)
      clinic.refresh()
    } catch (err) {
      notify(err.message, 'error')
    } finally {
      setCancellingId(null)
    }
  }

  const voiceProps = {
    status: voice.status,
    muted: voice.muted,
    startedAt: voice.startedAt,
    transcript: voice.transcript,
    error: voice.error,
    remoteStream: voice.remoteStream,
    localStream: voice.localStream,
    onStart: voice.startCall,
    onEnd: voice.endCall,
    onMute: voice.toggleMute,
  }

  if (!displayName) {
    return <ProfileEntry onSave={setDisplayName} />
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <Sidebar />
      <div className="main">
        <Header />
        {page === PAGES.DASHBOARD ? <DashboardPage clinic={clinic} displayName={displayName} onCancel={setCancelTarget} /> : null}
        {page === PAGES.DOCTORS ? <DoctorsPage clinic={clinic} /> : null}
        {page === PAGES.AVAILABILITY ? <AvailabilityPage clinic={clinic} onBook={handleBook} booking={booking} /> : null}
        {page === PAGES.APPOINTMENTS ? (
          <AppointmentsPage
            clinic={clinic}
            onCancel={setCancelTarget}
            cancellingId={cancellingId}
          />
        ) : null}
        {page === PAGES.VOICE ? <VoiceAssistantPage voice={voiceProps} /> : null}
        {page === PAGES.GUIDANCE ? <AppointmentGuidancePage /> : null}
        {page === PAGES.HISTORY ? <CallHistoryPage /> : null}
      </div>
      <Toasts />
      {cancelTarget ? (
        <CancelModal
          appointment={cancelTarget}
          submitting={cancellingId === cancelTarget.id}
          onClose={() => setCancelTarget(null)}
          onConfirm={handleCancel}
        />
      ) : null}
    </div>
  )
}

function ProfileEntry({ onSave }) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  return (
    <main className="profile-entry-shell">
      <form className="profile-entry card" onSubmit={(event) => {
        event.preventDefault()
        const value = name.trim()
        if (!value) { setError('Please enter your name to continue.'); return }
        onSave(value)
      }}>
        <span className="brand-mark" aria-hidden="true">V</span>
        <p className="eyebrow">VeyaCare profile</p>
        <h1>Welcome to VeyaCare</h1>
        <p className="lede">What should we call you? This display name is saved on this device and personalises your dashboard. It does not sign you in or verify your identity.</p>
        <label className="search">Your name
          <input autoFocus required value={name} onChange={(event) => { setName(event.target.value); setError('') }} placeholder="Enter your name" />
        </label>
        {error ? <p className="banner error" role="alert">{error}</p> : null}
        <button className="primary">Continue</button>
      </form>
    </main>
  )
}

export default function App() {
  return (
    <AppProvider>
      <ClinicApp />
    </AppProvider>
  )
}
