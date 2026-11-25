import { useApp } from '../hooks/useApp'
import { PAGES } from '../routes'

const GUIDANCE = [
  ['Bring relevant records', 'Keep previous prescriptions, test results and referral notes ready for your clinician.'],
  ['Arrive a little early', 'Allow time for check-in and any clinic forms before your appointment.'],
  ['Review the booking', 'Check the doctor, date and time in your appointment details before travelling.'],
  ['For urgent concerns', 'Contact the clinic or local emergency services for urgent medical needs. This page is general appointment guidance, not medical advice.'],
]

export function AppointmentGuidancePage() {
  const { setPage } = useApp()
  return (
    <div className="page-stack">
      <section className="page-intro">
        <div><p className="eyebrow">Helpful notes</p><h1>Appointment guidance</h1><p className="lede">A few practical reminders to make your clinic visit easier.</p></div>
      </section>
      <section className="guidance-page-grid">
        {GUIDANCE.map(([title, body], index) => (
          <article className="guidance-card" key={title}>
            <span className={`guidance-number guidance-${index}`} aria-hidden="true">{String(index + 1).padStart(2, '0')}</span>
            <h2>{title}</h2><p>{body}</p>
          </article>
        ))}
      </section>
      <button className="primary guidance-book" onClick={() => setPage(PAGES.AVAILABILITY)}>Book an appointment</button>
    </div>
  )
}
