export const PATIENT_PHONE_KEY = 'veyacare:patient-phone'

const INDIAN_MOBILE = /^[6-9][0-9]{9}$/

export function isValidIndianMobile(phone) {
  return typeof phone === 'string' && phone.length === 10 && INDIAN_MOBILE.test(phone)
}

export function appointmentsForPatient(appointments, phone) {
  if (!isValidIndianMobile(phone) || !Array.isArray(appointments)) return []
  // The API scopes records by the query phone but omits phone_number from its
  // response. When a response includes it (e.g. local adapter fixtures), keep
  // the defensive exact-match filter as well.
  return appointments.filter((appointment) => !appointment.phone_number || appointment.phone_number === phone)
}

export function appointmentStatusLabel(status) {
  if (status === 'booked') return 'Booked'
  if (status === 'cancelled') return 'Cancelled'
  return status
}

export function redactPhoneText(text) {
  if (typeof text !== 'string') return text
  return text.replace(/(^|\D)([6-9](?:[\s.-]?\d){9})(?=\D|$)/g, (_match, prefix) => `${prefix}••••••••••`)
}

export function readSavedPatientPhone(storage) {
  try {
    const phone = (storage ?? window.localStorage).getItem(PATIENT_PHONE_KEY) || ''
    return isValidIndianMobile(phone) ? phone : ''
  } catch {
    return ''
  }
}

export function saveConfirmedPatientPhone(phone, storage) {
  if (!isValidIndianMobile(phone)) return false
  try {
    const target = storage ?? window.localStorage
    target.setItem(PATIENT_PHONE_KEY, phone)
    return true
  } catch {
    return false
  }
}

export function clearSavedPatientPhone(storage) {
  try {
    const target = storage ?? window.localStorage
    target.removeItem(PATIENT_PHONE_KEY)
    return true
  } catch {
    return false
  }
}
