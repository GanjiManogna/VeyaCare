import { useMemo, useState } from 'react'
import { DoctorGrid } from '../components/doctors/DoctorGrid'
import { EmptyState, ErrorBanner, Loader } from '../components/common/Loader'
import { useApp } from '../hooks/useApp'
import { PAGES } from '../routes'

export function DoctorsPage({ clinic }) {
  const { setPage } = useApp()
  const [query, setQuery] = useState('')
  const [speciality, setSpeciality] = useState('')

  const specialities = useMemo(
    () => [...new Set(clinic.doctors.map((doctor) => doctor.speciality))],
    [clinic.doctors],
  )

  const visible = clinic.doctors.filter((doctor) => {
    const haystack = `${doctor.name} ${doctor.speciality}`.toLowerCase()
    const matchesQuery = haystack.includes(query.trim().toLowerCase())
    const matchesSpeciality = !speciality || doctor.speciality === speciality
    return matchesQuery && matchesSpeciality
  })
  const doctorAvailability = clinic.allAvailability?.length
    ? clinic.allAvailability
    : clinic.availability

  function openAvailability(doctor, slot) {
    const date = slot?.date || ''
    clinic.setFilters((current) => ({
      ...current,
      speciality: doctor.speciality || '',
      date,
    }))
    setPage(PAGES.AVAILABILITY, { query: { speciality: doctor.speciality || '', ...(date ? { date } : {}) } })
  }

  return (
    <div className="page-stack">
      <ErrorBanner message={clinic.error} />
      <section className="page-intro">
        <div>
          <p className="eyebrow">Directory</p>
          <h1>Doctors</h1>
          <p className="lede">
            Browse the clinic team and open the times they still have free.
          </p>
        </div>
      </section>
      {clinic.refreshing ? <p className="refresh-note">Updating clinic data…</p> : null}
      <div className="toolbar">
        <label className="search">
          Search
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Name or speciality"
          />
        </label>
        <div className="chip-row" role="group" aria-label="Filter by speciality">
          <button
            className={`filter-chip ${speciality === '' ? 'active' : ''}`}
            aria-pressed={speciality === ''}
            onClick={() => setSpeciality('')}
          >
            All
          </button>
          {specialities.map((item) => (
            <button
              key={item}
              className={`filter-chip ${speciality === item ? 'active' : ''}`}
              aria-pressed={speciality === item}
              onClick={() => setSpeciality(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {clinic.loading && clinic.doctors.length === 0 ? (
        <Loader label="Loading doctors…" />
      ) : null}
      {!clinic.loading && !clinic.error && clinic.doctors.length === 0 ? (
        <EmptyState
          title="No doctors found"
          body="The clinic directory is empty right now."
        />
      ) : null}
      {!clinic.loading && clinic.doctors.length > 0 && visible.length === 0 ? (
        <EmptyState
          title="No matching doctors"
          body="Try another name or speciality. The list uses the doctors returned by the clinic."
        />
      ) : null}
      {visible.length > 0 ? (
        <DoctorGrid
          doctors={visible}
          availability={doctorAvailability}
          availabilityError={clinic.availabilityError}
          loading={false}
          error={clinic.error}
          onSelect={openAvailability}
        />
      ) : null}
    </div>
  )
}
