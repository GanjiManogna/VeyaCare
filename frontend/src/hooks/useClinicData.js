import { useCallback, useEffect, useState } from 'react'
import { getAppointments, getAvailability, getDoctors, getVisitReasons, getHealthConcerns } from '../api/client'
import { pageFromLocation, PAGES } from '../routes'
import { appointmentsForPatient, clearSavedPatientPhone, PATIENT_PHONE_KEY, readSavedPatientPhone, saveConfirmedPatientPhone } from '../utils/patientLookup'

export function useClinicData() {
  const [doctors, setDoctors] = useState([])
  const [appointments, setAppointments] = useState([])
  const [availability, setAvailability] = useState([])
  const [allAvailability, setAllAvailability] = useState([])
  const [visitReasons, setVisitReasons] = useState({})
  const [healthConcerns, setHealthConcerns] = useState([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [appointmentsLoading, setAppointmentsLoading] = useState(false)
  const [error, setError] = useState('')
  const [availabilityError, setAvailabilityError] = useState('')
  const [appointmentsError, setAppointmentsError] = useState('')
  const [patientPhone, setPatientPhone] = useState(readSavedPatientPhone)
  const [filters, setFilters] = useState(() => {
    const params = new URLSearchParams(window.location.search)
    return { speciality: params.get('speciality') || '', date: params.get('date') || '' }
  })
  const [reloadToken, setReloadToken] = useState(0)

  const applyPatientPhone = useCallback((phone) => {
    setAppointments([])
    setAppointmentsError('')
    setAppointmentsLoading(Boolean(phone))
    setPatientPhone(phone)
  }, [])
  const rememberPatientPhone = useCallback((phone) => {
    if (!saveConfirmedPatientPhone(phone)) return false
    applyPatientPhone(phone)
    return true
  }, [applyPatientPhone])
  const forgetPatientPhone = useCallback(() => {
    clearSavedPatientPhone()
    applyPatientPhone('')
  }, [applyPatientPhone])
  const refresh = useCallback(() => setReloadToken((token) => token + 1), [])
  const updateAppointmentStatus = useCallback((id, status) => {
    setAppointments((current) => current.map((item) => item.id === id ? { ...item, status } : item))
  }, [])

  useEffect(() => {
    function syncFiltersFromRoute() {
      if (pageFromLocation() !== PAGES.AVAILABILITY) return
      const params = new URLSearchParams(window.location.search)
      setFilters((current) => ({ ...current, speciality: params.get('speciality') || '', date: params.get('date') || '' }))
    }
    window.addEventListener('popstate', syncFiltersFromRoute)
    window.addEventListener('veyacare:navigate', syncFiltersFromRoute)
    return () => {
      window.removeEventListener('popstate', syncFiltersFromRoute)
      window.removeEventListener('veyacare:navigate', syncFiltersFromRoute)
    }
  }, [])

  useEffect(() => {
    function syncPatientPhone(event) {
      if (event.key !== null && event.key !== PATIENT_PHONE_KEY) return
      applyPatientPhone(readSavedPatientPhone())
    }
    window.addEventListener('storage', syncPatientPhone)
    return () => window.removeEventListener('storage', syncPatientPhone)
  }, [applyPatientPhone])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setRefreshing(true)
      setAppointmentsLoading(Boolean(patientPhone))
      try {
        const filteredAvailability = getAvailability({ speciality: filters.speciality || undefined, date: filters.date || undefined })
        const unfilteredAvailability = filters.speciality || filters.date ? getAvailability() : filteredAvailability
        const requests = [getDoctors(), filteredAvailability, unfilteredAvailability, getVisitReasons(), getHealthConcerns()]
        if (patientPhone) requests.push(getAppointments(patientPhone))
        // Keep independent clinic data usable when an unrelated endpoint (most
        // commonly appointment lookup) fails. A single rejected Promise.all
        // used to leave doctors and real slot data stuck in their empty state.
        const results = await Promise.allSettled(requests)
        if (cancelled) return
        const [doctorResult, availabilityResult, allAvailabilityResult, reasonResult, concernResult, appointmentResult] = results
        const message = (result, fallback) => result.status === 'rejected'
          ? (result.reason?.message || fallback)
          : ''

        if (doctorResult.status === 'fulfilled') setDoctors(Array.isArray(doctorResult.value) ? doctorResult.value : [])
        if (availabilityResult.status === 'fulfilled') setAvailability(Array.isArray(availabilityResult.value) ? availabilityResult.value : [])
        if (allAvailabilityResult.status === 'fulfilled') setAllAvailability(Array.isArray(allAvailabilityResult.value) ? allAvailabilityResult.value : [])
        if (reasonResult.status === 'fulfilled') setVisitReasons(reasonResult.value && typeof reasonResult.value === 'object' ? reasonResult.value : {})
        if (concernResult.status === 'fulfilled') setHealthConcerns(Array.isArray(concernResult.value) ? concernResult.value : [])
        if (patientPhone && appointmentResult?.status === 'fulfilled') setAppointments(appointmentsForPatient(appointmentResult.value, patientPhone))
        else if (!patientPhone) setAppointments([])

        const doctorErrorMessage = message(doctorResult, 'Unable to load the doctor directory.')
        const availabilityErrorMessage = message(availabilityResult, 'Unable to load appointment availability.')
        const auxiliaryError = message(reasonResult, 'Unable to load visit reasons.') || message(concernResult, 'Unable to load health concerns.')
        setError(doctorErrorMessage || auxiliaryError)
        setAvailabilityError(availabilityErrorMessage)
        const appointmentErrorMessage = patientPhone ? message(appointmentResult, 'Unable to load this patient’s appointments.') : ''
        setAppointmentsError(appointmentErrorMessage)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Unable to load clinic data.')
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
          setRefreshing(false)
          setAppointmentsLoading(false)
        }
      }
    }
    load()
    return () => { cancelled = true }
  }, [filters.date, filters.speciality, patientPhone, reloadToken])

  return {
    doctors, appointments, availability, allAvailability, visitReasons, healthConcerns, loading, refreshing,
    appointmentsLoading, appointmentsError, availabilityError, patientPhone, rememberPatientPhone, forgetPatientPhone,
    updateAppointmentStatus, error, filters, setFilters, refresh,
  }
}
