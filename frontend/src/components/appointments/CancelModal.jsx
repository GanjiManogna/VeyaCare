import { useState } from 'react'

export function CancelModal({ appointment, onClose, onConfirm, submitting }) {
  const [phoneNumber, setPhoneNumber] = useState('')

  if (!appointment) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form
        className="modal card"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => {
          event.preventDefault()
          onConfirm({
            appointment_id: appointment.id,
            phone_number: phoneNumber,
          })
        }}
      >
        <h3>Cancel this visit?</h3>
        <p>
          {appointment.doctor}, {appointment.speciality}, on {appointment.date} at{' '}
          {appointment.time}. Enter the booking phone number to verify the cancellation request.
        </p>
        <label>
          Confirm mobile number
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
            title="Enter exactly 10 digits, starting with 6, 7, 8 or 9"
            placeholder="10-digit mobile number"
          />
        </label>
        <div className="call-actions">
          <button type="button" className="ghost" onClick={onClose}>
            Keep appointment
          </button>
          <button className="danger" disabled={submitting}>
            {submitting ? 'Cancelling…' : 'Confirm cancel'}
          </button>
        </div>
      </form>
    </div>
  )
}
