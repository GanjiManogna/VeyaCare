import { useApp } from '../hooks/useApp'
import { AppointmentList } from '../components/appointments/AppointmentList'
import { DoctorGrid } from '../components/doctors/DoctorGrid'
import { EmptyState, ErrorBanner, Loader } from '../components/common/Loader'
import { PAGES } from '../routes'
import { openSlotsFor } from '../utils/format'

function appointmentDateTime(item) {
  const [clock, period] = String(item.time || '').split(' ')
  const [hours, minutes] = (clock || '').split(':').map(Number)
  if (!item.date || !hours || minutes === undefined || !period) return Number.MAX_SAFE_INTEGER
  const normalizedHours = period.toUpperCase() === 'PM' ? (hours % 12) + 12 : hours % 12
  return new Date(`${item.date}T${String(normalizedHours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:00`).getTime()
}

function localToday() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

function formatToday() {
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())
}

export function DashboardPage({ clinic, onCancel, displayName }) {
  const { setPage } = useApp()
  const patientAppointments = clinic.appointments
  const allAvailability = clinic.allAvailability || clinic.availability
  const currentTime = new Date().getTime()
  const booked = patientAppointments.filter((item) => item.status === 'booked')
  const upcoming = booked
    .filter((item) => item.date >= localToday() && appointmentDateTime(item) >= currentTime)
    .sort((left, right) => appointmentDateTime(left) - appointmentDateTime(right))
  const specialties = [...new Set(clinic.doctors.map((doctor) => doctor.speciality))].sort()
  const availableDoctorCount = allAvailability.length
  const metrics = [
    { label: 'Booked appointments', value: clinic.patientPhone ? booked.length : '—', hint: clinic.patientPhone ? 'Your booked visits' : 'Look up by patient mobile', page: PAGES.APPOINTMENTS, tone: 'blue' },
    { label: 'Upcoming visits', value: clinic.patientPhone ? upcoming.length : '—', hint: clinic.patientPhone ? 'Your future visits' : 'Look up by patient mobile', page: PAGES.APPOINTMENTS, tone: 'teal' },
    { label: 'Available doctors', value: availableDoctorCount, hint: 'With open slots', page: PAGES.DOCTORS, tone: 'violet' },
    { label: 'Specialities', value: specialties.length, hint: 'In the directory', page: PAGES.DOCTORS, tone: 'coral' },
  ]

  function openAvailability(doctor, slot) {
    const speciality = doctor?.speciality || ''
    const date = slot?.date || ''
    clinic.setFilters((current) => ({ ...current, speciality, date }))
    setPage(PAGES.AVAILABILITY, { query: { ...(speciality ? { speciality } : {}), ...(date ? { date } : {}) } })
  }

  function openSpeciality(speciality) {
    clinic.setFilters((current) => ({ ...current, speciality, date: '' }))
    setPage(PAGES.AVAILABILITY, { query: { speciality } })
  }

  const hasCachedClinicData = clinic.doctors.length + patientAppointments.length + allAvailability.length > 0
  const ready = !clinic.loading && (!clinic.error || hasCachedClinicData)

  return (
    <div className="page-stack dashboard dashboard-v2">
      {clinic.error ? (
        <div className="dashboard-error">
          <ErrorBanner message={clinic.error} />
          <button className="ghost" onClick={clinic.refresh}>Retry loading clinic data</button>
        </div>
      ) : null}
      {clinic.appointmentsError ? <ErrorBanner message={clinic.appointmentsError} /> : null}

      <section className="dashboard-welcome">
        <div className="welcome-copy">
          <p className="eyebrow light">VeyaCare · {formatToday()}</p>
          <h1>Good to see you, {displayName}.</h1>
          <p>Take a moment for your health. Find the right clinician or manage an appointment whenever it suits you.</p>
          <div className="welcome-actions">
            <button className="primary" onClick={() => setPage(PAGES.AVAILABILITY)}>Book an appointment</button>
            <button className="welcome-secondary" onClick={() => setPage(PAGES.APPOINTMENTS)}>My appointments</button>
          </div>
        </div>
        <div className="welcome-aside" aria-hidden="true">
          <span className="welcome-orbit orbit-one" />
          <span className="welcome-orbit orbit-two" />
          <span className="welcome-symbol">+</span>
          <span className="welcome-note">Care, thoughtfully connected</span>
        </div>
      </section>

      <section className="dashboard-overview" aria-labelledby="overview-title">
        <div className="dashboard-section-title">
          <div><p className="eyebrow">At a glance</p><h2 id="overview-title">Clinic overview</h2></div>
          {clinic.refreshing ? <span className="refresh-note">Updating…</span> : null}
        </div>
        <div className="overview-grid">
          {metrics.map((metric) => (
            <button key={metric.label} className={`overview-card ${metric.tone}`} onClick={() => setPage(metric.page)} aria-label={`${metric.label}: ${ready ? metric.value : clinic.loading ? 'loading' : 'unavailable'}. Open ${metric.page === PAGES.APPOINTMENTS ? 'appointments' : 'doctor directory'}`}>
              <span className="overview-icon" aria-hidden="true"><OverviewIcon type={metric.tone} /></span>
              {ready ? <strong>{metric.value}</strong> : clinic.loading ? <span className="stat-skeleton" aria-label="Loading" /> : <span className="overview-unavailable" aria-label="Unavailable">—</span>}
              <span className="overview-label">{metric.label}</span>
              <span className="overview-hint">{metric.hint} <span aria-hidden="true">↗</span></span>
            </button>
          ))}
        </div>
        {!clinic.loading && !clinic.error && clinic.doctors.length === 0 ? (
          <p className="dashboard-empty-note">The doctor directory is empty. Clinic data will appear here when available.</p>
        ) : null}
      </section>

      <section className="dashboard-section upcoming-section" aria-labelledby="upcoming-title">
        <div className="dashboard-section-title">
          <div><p className="eyebrow">Plan ahead</p><h2 id="upcoming-title">Next appointment</h2></div>
          <button className="text-link" onClick={() => setPage(PAGES.APPOINTMENTS)}>View all appointments <span aria-hidden="true">→</span></button>
        </div>
        {clinic.patientPhone && clinic.appointmentsLoading ? <Loader label="Loading upcoming appointments…" /> : (clinic.error || clinic.appointmentsError) && patientAppointments.length === 0 ? (
          <EmptyState title="Appointments unavailable" body="We couldn't load the schedule. Use the retry button above to try again." />
        ) : upcoming.length > 0 ? (
          <AppointmentList appointments={[upcoming[0]]} loading={false} onCancel={onCancel} />
        ) : !clinic.patientPhone ? (
          <EmptyState title="Find your appointment" body="Look up your visits by patient mobile number in My appointments. The display name does not identify a patient." />
        ) : (
          <div className="dashboard-empty-card">
            <EmptyState title="No upcoming booked appointments" body="When a visit is booked, the next appointment will appear here." />
            <button className="primary" onClick={() => setPage(PAGES.AVAILABILITY)}>Find an appointment</button>
          </div>
        )}
      </section>

      <section className="dashboard-section doctor-section" aria-labelledby="featured-doctors-title">
        <div className="dashboard-section-title">
          <div><p className="eyebrow">Care team</p><h2 id="featured-doctors-title">Find a doctor</h2></div>
          <button className="text-link" onClick={() => setPage(PAGES.DOCTORS)}>View all doctors <span aria-hidden="true">→</span></button>
        </div>
        {clinic.loading && clinic.doctors.length === 0 ? <Loader label="Loading doctors…" /> : null}
        {clinic.error && clinic.doctors.length === 0 ? <EmptyState title="Doctor directory unavailable" body="Retry clinic data to see doctors." /> : null}
        {!clinic.loading && clinic.doctors.length === 0 && !clinic.error ? <EmptyState title="No doctors listed yet" body="The clinic directory will appear here when available." /> : null}
        {clinic.doctors.length > 0 ? (
          <DoctorGrid doctors={clinic.doctors.slice(0, 4)} availability={allAvailability} loading={false} error={clinic.error} availabilityError={clinic.availabilityError} onSelect={openAvailability} />
        ) : null}
      </section>

      <section className="dashboard-section specialty-section" aria-labelledby="specialties-title">
        <div className="dashboard-section-title"><div><p className="eyebrow">Browse by care</p><h2 id="specialties-title">Specialities</h2></div></div>
        {clinic.loading && specialties.length === 0 ? <Loader label="Loading specialities…" /> : null}
        {specialties.length > 0 ? (
          <div className="specialty-grid">
            {specialties.map((speciality, index) => {
              const doctorsInSpeciality = clinic.doctors.filter((doctor) => doctor.speciality === speciality)
              const availableInSpeciality = doctorsInSpeciality.filter((doctor) => openSlotsFor(allAvailability, doctor.id) > 0).length
              return (
                <button key={speciality} className={`specialty-card accent-${index % 5}`} onClick={() => openSpeciality(speciality)}>
                  <span className="specialty-glyph" aria-hidden="true"><SpecialtyIcon speciality={speciality} /></span>
                  <strong>{speciality}</strong>
                  <span>{availableInSpeciality} {availableInSpeciality === 1 ? 'doctor' : 'doctors'} with open times</span>
                  <span className="specialty-arrow" aria-hidden="true">↗</span>
                </button>
              )
            })}
          </div>
        ) : clinic.error ? <EmptyState title="Specialities unavailable" body="Retry clinic data to load the speciality list." /> : !clinic.loading ? <EmptyState title="No specialities available" body="Specialities appear with the clinic doctor directory." /> : null}
      </section>

    </div>
  )
}

function OverviewIcon({ type }) {
  const paths = {
    blue: <><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M8 3v4M16 3v4M4 10h16" /></>,
    teal: <><circle cx="12" cy="12" r="8" /><path d="M12 7v5l3 2" /></>,
    violet: <><circle cx="9" cy="8" r="3" /><path d="M3 19c1-3 3-4.5 6-4.5s5 1.5 6 4.5M16 5.5a3 3 0 0 1 0 5.8m1 3.4c2 .6 3.3 2 4 4.3" /></>,
    coral: <><path d="M12 3v18M3 12h18" /><circle cx="12" cy="12" r="8" /></>,
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{paths[type]}</svg>
}

function SpecialtyIcon({ speciality }) {
  const name = speciality.toLowerCase()
  if (name.includes('cardio')) return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M20 8.5c0 5-8 11-8 11s-8-6-8-11a4.5 4.5 0 0 1 8-2.8 4.5 4.5 0 0 1 8 2.8Z"/><path d="M4 12h4l2-3 3 6 2-3h5"/></svg>
  if (name.includes('neuro')) return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4a4 4 0 0 0-7 2.6A4 4 0 0 0 4 14a4 4 0 0 0 5 5h3m0-15a4 4 0 0 1 7 2.6 4 4 0 0 1 1 7.4 4 4 0 0 1-5 5h-3m0-15v15m-4-9h4m4-2h-4"/></svg>
  if (name.includes('pediatric')) return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v8m-4-4h8"/><circle cx="9" cy="10" r=".5" fill="currentColor"/><circle cx="15" cy="10" r=".5" fill="currentColor"/></svg>
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="8"/><path d="M12 8v8m-4-4h8"/></svg>
}
