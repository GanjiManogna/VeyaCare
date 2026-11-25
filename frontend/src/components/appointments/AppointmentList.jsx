import { EmptyState, Loader } from '../common/Loader'
import { appointmentStatusLabel } from '../../utils/patientLookup'

export function AppointmentList({
  appointments,
  loading,
  onCancel,
  cancellingId,
  error,
}) {
  if (loading && !appointments.length) return <Loader label="Loading appointments…" />
  if (!appointments.length) {
    if (error) return null
    return (
      <EmptyState
        title="No appointments yet"
        body="Book an open time, or ask the receptionist during a call."
      />
    )
  }

  return (
    <div className="visit-list">
      {appointments.map((appointment) => (
        <article key={appointment.id} className="visit">
          <div className="visit-when">
            <strong>{appointment.time}</strong>
            <span>{appointment.date}</span>
          </div>
          <div className="visit-body">
            <h3>{appointment.doctor}</h3>
            <p className="speciality">{appointment.speciality}</p>
            {appointment.consultation_fee !== null && appointment.consultation_fee !== undefined ? <p>Consultation fee: ₹{appointment.consultation_fee}</p> : null}
            {appointment.patient_name ? (
              <p><strong>For {appointment.patient_name}</strong></p>
            ) : (
              <p className="muted">Patient name not provided</p>
            )}
            {appointment.booked_by_name && appointment.booked_by_name !== appointment.patient_name ? (
              <p className="muted">Arranged by {appointment.booked_by_name}</p>
            ) : null}
            {(appointment.health_concern || appointment.visit_reason) ? <p>Health concern: {appointment.health_concern || appointment.visit_reason}{appointment.health_concern_details || appointment.visit_reason_details ? ` · ${appointment.health_concern_details || appointment.visit_reason_details}` : ''}</p> : null}
            {appointment.appointment_reference ? <p>Reference: <strong>{appointment.appointment_reference}</strong></p> : null}
            {appointment.checkin_code ? <p>In-person check-in code: <strong>{appointment.checkin_code}</strong></p> : null}
          </div>
          <div className="visit-actions">
            <span className={`chip ${appointment.status}`}>{appointmentStatusLabel(appointment.status)}</span>
            {appointment.status === 'booked' && onCancel ? (
              <button
                className="danger text"
                disabled={cancellingId === appointment.id}
                onClick={() => onCancel(appointment)}
              >
                {cancellingId === appointment.id ? 'Cancelling…' : 'Cancel visit'}
              </button>
            ) : null}
          </div>
        </article>
      ))}
    </div>
  )
}
