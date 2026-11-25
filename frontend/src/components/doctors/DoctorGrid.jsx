import { EmptyState, Loader } from '../common/Loader'
import { initials, openSlotsFor } from '../../utils/format'

export function DoctorGrid({
  doctors,
  availability = [],
  loading,
  onSelect,
  error,
  availabilityError = '',
}) {
  if (loading && !doctors.length) return <Loader label="Loading doctors…" />
  if (!doctors.length) {
    if (error) return null
    return (
      <EmptyState
        title="No doctors found"
        body="The clinic directory is empty right now."
      />
    )
  }

  return (
    <div className="doctor-grid">
      {doctors.map((doctor) => {
        const doctorAvailability = availability.find((item) => String(item.doctor_id) === String(doctor.id))
        const openSlots = doctorAvailability?.available_slots || []
        const slots = openSlotsFor(availability, doctor.id)
        return (
          <article key={doctor.id} className="doctor-card">
            <div className="doctor-top">
              <span className="avatar">{initials(doctor.name)}</span>
              <p className="slot-count">
                {slots === 1 ? '1 open slot' : `${slots} open slots`}
              </p>
            </div>
            <h3>{doctor.name}</h3>
            <p className="speciality">{doctor.speciality}</p>
            {Number.isFinite(doctor.experience) ? <p className="muted">{doctor.experience} years of experience</p> : null}
            <p className="doctor-fee">{Number.isFinite(doctor.consultation_fee) ? <>₹{doctor.consultation_fee} <span>consultation</span></> : <span>Consultation fee unavailable</span>}</p>
            {openSlots.length > 0 ? (
              <div className="doctor-open-slots" aria-label={`Available appointment times for ${doctor.name}`}>
                {openSlots.slice(0, 2).map((slot) => (
                  <button key={slot.slot_id} className="doctor-open-slot" onClick={() => onSelect?.(doctor, slot)}>
                    {slot.date} · {slot.time}
                  </button>
                ))}
                {openSlots.length > 2 ? <span className="doctor-open-slot more">+{openSlots.length - 2} more</span> : null}
              </div>
            ) : <p className="muted">{availabilityError ? 'Availability could not be loaded' : 'No open times in this view'}</p>}
            {onSelect ? (
              <button className="text-link" onClick={() => onSelect(doctor)}>
                Browse available times <span aria-hidden="true">→</span>
              </button>
            ) : null}
          </article>
        )
      })}
    </div>
  )
}
