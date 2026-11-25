import { AvailabilityPanel } from '../components/availability/AvailabilityPanel'
import { ErrorBanner } from '../components/common/Loader'

export function AvailabilityPage({ clinic, onBook, booking }) {
  return (
    <div className="page-stack">
      <ErrorBanner message={clinic.error || clinic.availabilityError} />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Find a time</p>
          <h1>Doctor availability</h1>
          <p className="lede">Choose from live appointment slots returned by the clinic.</p>
        </div>
      </section>
      {clinic.refreshing ? <p className="refresh-note">Updating clinic data…</p> : null}
      <AvailabilityPanel
        doctors={clinic.doctors}
        availability={clinic.availability}
        loading={clinic.loading}
        error={clinic.error}
        filters={clinic.filters}
        setFilters={clinic.setFilters}
        onBook={onBook}
        booking={booking}
        healthConcerns={clinic.healthConcerns}
      />
    </div>
  )
}
