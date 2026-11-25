import { AppointmentList } from '../components/appointments/AppointmentList'
import { ErrorBanner, EmptyState, Loader } from '../components/common/Loader'

export function AppointmentsPage({ clinic, onCancel, cancellingId }) {
  const appointmentsLoading = clinic.appointmentsLoading || (clinic.loading && Boolean(clinic.patientPhone))
  const bookedCount = clinic.appointments.filter((item) => item.status === 'booked').length
  const cancelledCount = clinic.appointments.filter((item) => item.status === 'cancelled').length

  return (
    <div className="page-stack">
      <ErrorBanner message={clinic.appointmentsError || clinic.error} />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Your care schedule</p>
          <h1>My appointments</h1>
          <p className="lede">Your appointment history uses a patient mobile number saved on this device. This local lookup preference does not verify identity.</p>
        </div>
        {clinic.patientPhone ? <button className="ghost" onClick={clinic.forgetPatientPhone}>Forget saved lookup number</button> : null}
      </section>

      {appointmentsLoading ? <Loader label="Loading your appointments…" /> : null}
      {clinic.appointmentsError ? <button className="ghost" onClick={clinic.refresh}>Retry loading appointments</button> : null}
      {!appointmentsLoading && !clinic.appointmentsError && !clinic.patientPhone ? (
        <EmptyState
          title="No saved appointment lookup yet"
          body="Complete a booking first. When it succeeds, this device saves the patient mobile number as a private lookup preference and displays the matching appointment history here."
        />
      ) : null}
      {!appointmentsLoading && clinic.patientPhone && !clinic.appointmentsError ? (
        <section className="card">
          <div className="section-head appointment-section-head">
            <div>
              <p className="eyebrow">Patient schedule</p>
              <h2>Appointments</h2>
            </div>
            <div className="appointment-counts" aria-label="Appointment counts">
              <span className="chip booked">{bookedCount} booked</span>
              <span className="chip cancelled">{cancelledCount} cancelled</span>
            </div>
          </div>
          {clinic.appointments.length === 0 ? (
            <EmptyState title="No appointments found" body="There are no booked or cancelled appointments for the saved patient number." />
          ) : (
            <AppointmentList appointments={clinic.appointments} loading={false} onCancel={onCancel} cancellingId={cancellingId} />
          )}
        </section>
      ) : null}
    </div>
  )
}
