const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8001').replace(/\/+$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    const detail =
      typeof payload === 'object' && payload?.detail
        ? payload.detail
        : `Request failed with status ${response.status}`
    const error = new Error(typeof detail === 'object' && detail?.message
      ? detail.message
      : typeof detail === 'string' ? detail : JSON.stringify(detail))
    error.status = response.status
    error.payload = payload
    if (detail && typeof detail === 'object') Object.assign(error, detail)
    throw error
  }

  return payload
}

export function getApiBase() {
  return API_BASE
}

export function getHealth() {
  return request('/health')
}

export function getDoctors() {
  return request('/api/doctors')
}

export function getVisitReasons() {
  return request('/api/visit-reasons')
}

export function getHealthConcerns() {
  return request('/api/health-concerns')
}

export function getAvailability({ speciality, date } = {}) {
  const params = new URLSearchParams()
  if (speciality) params.set('speciality', speciality)
  if (date) params.set('date', date)
  const query = params.toString()
  return request(`/api/availability${query ? `?${query}` : ''}`)
}

export function getAppointments(phoneNumber) {
  const params = new URLSearchParams()
  if (phoneNumber) params.set('phone_number', phoneNumber)
  const query = params.toString()
  return request(`/api/appointments${query ? `?${query}` : ''}`)
}

export function bookAppointment({ phone_number, doctor_id, slot_id, patient_name, booked_by_name, visit_reason, visit_reason_details, health_concern, health_concern_details }) {
  return request('/api/appointments', {
    method: 'POST',
    body: JSON.stringify({
      phone_number,
      doctor_id,
      slot_id,
      patient_name: patient_name || null,
      booked_by_name: booked_by_name || null,
      visit_reason,
      visit_reason_details: visit_reason_details || null,
      health_concern,
      health_concern_details: health_concern_details || null,
    }),
  })
}

export function cancelAppointment({ phone_number, appointment_id }) {
  return request('/api/appointments/cancel', {
    method: 'POST',
    body: JSON.stringify({
      phone_number,
      appointment_id,
    }),
  })
}

export function postWebRtcOffer(body) {
  return request('/api/offer', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchWebRtcIce(body) {
  return request('/api/offer', {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}
