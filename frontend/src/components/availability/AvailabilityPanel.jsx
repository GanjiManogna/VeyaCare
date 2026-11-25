import { useMemo, useState } from 'react'
import { EmptyState, Loader } from '../common/Loader'

export function AvailabilityPanel({
  doctors,
  availability,
  loading,
  error,
  filters,
  setFilters,
  onBook,
  booking,
  healthConcerns = [],
}) {
  const [selectedSlot, setSelectedSlot] = useState(null)
  const [patientName, setPatientName] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [patientType, setPatientType] = useState('self')
  const [healthConcern, setHealthConcern] = useState('')
  const [healthConcernDetails, setHealthConcernDetails] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [formError, setFormError] = useState('')

  function changePatientType(value) {
    setPatientType(value)
    setPatientName('')
    setPhoneNumber('')
    setHealthConcern('')
    setHealthConcernDetails('')
    setFormError('')
  }

  const specialities = useMemo(
    () => [...new Set(doctors.map((doctor) => doctor.speciality))],
    [doctors],
  )

  return (
    <section className="card">
      <div className="section-head">
        <div>
          <p className="eyebrow">Open times</p>
          <h2>Doctor availability</h2>
        </div>
      </div>
      <div className="filters">
        <label>
          Speciality
          <select
            value={filters.speciality}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                speciality: event.target.value,
              }))
            }
          >
            <option value="">All</option>
            {specialities.map((speciality) => (
              <option key={speciality} value={speciality}>
                {speciality}
              </option>
            ))}
          </select>
        </label>
        <label>
          Date
          <input
            type="date"
            value={filters.date}
            onChange={(event) =>
              setFilters((current) => ({ ...current, date: event.target.value }))
            }
          />
        </label>
      </div>

      {loading && availability.length === 0 ? (
        <Loader label="Loading availability…" />
      ) : null}
      {!loading && !error && availability.length === 0 ? (
        <EmptyState
          title="No open slots"
          body="Try another date or speciality."
        />
      ) : null}

      <div className="availability-list">
        {availability.map((item) => (
          <article key={item.doctor_id} className="availability-row">
            <div>
              <h3>{item.doctor_name}</h3>
              <p className="muted">
                {item.speciality} · {item.experience} yrs · {Number.isFinite(item.consultation_fee) ? `₹${item.consultation_fee} consultation` : 'Consultation fee unavailable'}
              </p>
            </div>
            <div className="slots">
              {item.available_slots.map((slot) => {
                const active =
                  selectedSlot?.slot_id === slot.slot_id &&
                  selectedSlot?.doctor_id === item.doctor_id
                return (
                  <button
                    key={slot.slot_id}
                    className={`slot ${active ? 'active' : ''}`}
                    aria-pressed={active}
                    onClick={() =>
                      setSelectedSlot({
                        ...slot,
                        doctor_id: item.doctor_id,
                        doctor_name: item.doctor_name,
              speciality: item.speciality,
              experience: item.experience,
                        consultation_fee: item.consultation_fee,
                      })
                    }
                  >
                    {slot.date} · {slot.time}
                  </button>
                )
              })}
            </div>
          </article>
        ))}
      </div>

      {selectedSlot ? (
        <form
          className="book-form"
          onSubmit={async (event) => {
            event.preventDefault()
            if (!patientName.trim()) {
              setFormError("Enter the patient's full name.")
              return
            }
            if (!healthConcern) {
              setFormError('Choose a health concern category.')
              return
            }
            if (healthConcern === 'Other' && !healthConcernDetails.trim()) {
              setFormError('Briefly describe the concern selected as Other.')
              return
            }
            setFormError('')
            const booked = await onBook({
              phone_number: phoneNumber,
              doctor_id: selectedSlot.doctor_id,
              slot_id: selectedSlot.slot_id,
              patient_name: patientName.trim(),
              patient_type: patientType,
              visit_reason: healthConcern,
              visit_reason_details: healthConcernDetails.trim() || null,
              health_concern: healthConcern,
              health_concern_details: healthConcernDetails.trim() || null,
            })
            if (booked) {
              setConfirmation(booked)
              setSelectedSlot(null)
              setPatientName('')
              setPhoneNumber('')
              setPatientType('self')
              setHealthConcern('')
              setHealthConcernDetails('')
            }
          }}
        >
          <h3>Book {selectedSlot.doctor_name}</h3>
          <p className="muted">
            {selectedSlot.speciality} · {selectedSlot.date} at {selectedSlot.time} · {selectedSlot.experience} years' experience · {Number.isFinite(selectedSlot.consultation_fee) ? `₹${selectedSlot.consultation_fee} consultation` : 'Consultation fee unavailable'}
          </p>
          <fieldset className="patient-choice">
            <legend>Who is this appointment for?</legend>
            <label><input type="radio" name="patient-type" checked={patientType === 'self'} onChange={() => changePatientType('self')} /> For me</label>
            <label><input type="radio" name="patient-type" checked={patientType === 'other'} onChange={() => changePatientType('other')} /> For someone else</label>
          </fieldset>
          <label>
            Patient's full name
            <input required value={patientName} onChange={(event) => { setPatientName(event.target.value); setFormError('') }} placeholder="Full name of the patient" />
          </label>
          <label>
            Health concern (appointment routing only)
            <select value={healthConcern} onChange={(event) => { setHealthConcern(event.target.value); setFormError('') }} required>
              <option value="">Choose a category</option>
              {healthConcerns.map((concern) => <option key={concern} value={concern}>{concern}</option>)}
            </select>
          </label>
          {healthConcern === 'Other' ? (
            <label>
              Short description
              <textarea required maxLength={500} value={healthConcernDetails} onChange={(event) => setHealthConcernDetails(event.target.value)} placeholder="Describe briefly in your own words" />
            </label>
          ) : null}
          <p className="muted">These categories help route appointments. They are not diagnoses. For severe breathing difficulty, chest pain, stroke symptoms, uncontrolled bleeding or loss of consciousness, seek emergency care now.</p>
          <label>
            {patientType === 'other' ? "Patient's phone number" : 'Your mobile number'}
            <input
              required
              type="password"
              inputMode="numeric"
              autoComplete="off"
              minLength={10}
              maxLength={10}
              pattern="[6-9][0-9]{9}"
              value={phoneNumber}
              onChange={(event) => setPhoneNumber(event.target.value)}
              placeholder="10-digit mobile number"
              title="Enter exactly 10 digits, starting with 6, 7, 8 or 9"
            />
          </label>
          {formError ? <p className="banner error" role="alert">{formError}</p> : null}
          <button className="primary" disabled={booking}>
            {booking ? 'Booking…' : 'Book visit'}
          </button>
        </form>
      ) : null}
      {confirmation ? (
        <aside className="booking-confirmation" role="status">
          <p className="eyebrow">Appointment confirmed</p>
          <h3>{confirmation.doctor}</h3>
          <p>{confirmation.speciality} · {confirmation.date} at {confirmation.time}</p>
          <p>For {confirmation.patient_name || patientName}</p>
          {(confirmation.health_concern || confirmation.visit_reason) ? <p>Health concern: {confirmation.health_concern || confirmation.visit_reason}{confirmation.health_concern_details || confirmation.visit_reason_details ? ` · ${confirmation.health_concern_details || confirmation.visit_reason_details}` : ''}</p> : null}
          {Number.isFinite(confirmation.consultation_fee) ? <p>Consultation fee: ₹{confirmation.consultation_fee}</p> : null}
          <p>Reference: <strong>{confirmation.appointment_reference}</strong></p>
          <p>In-person check-in code: <strong>{confirmation.checkin_code}</strong></p>
          <button className="ghost" type="button" onClick={() => setConfirmation(null)}>Dismiss</button>
        </aside>
      ) : null}
    </section>
  )
}
