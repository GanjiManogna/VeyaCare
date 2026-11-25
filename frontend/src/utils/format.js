export function formatPhone(value) {
  const raw = String(value || '').trim()
  const digits = raw.replace(/\D/g, '')
  if (digits.length === 10) {
    return `${digits.slice(0, 5)} ${digits.slice(5)}`
  }
  if (digits.length > 10) {
    return `${digits.slice(0, digits.length - 10)} ${digits.slice(-10, -5)} ${digits.slice(-5)}`
  }
  return raw
}

export function initials(name) {
  const parts = String(name || '')
    .replace(/^Dr\.?\s+/i, '')
    .split(/\s+/)
    .filter(Boolean)
  const letters = parts.slice(0, 2).map((part) => part[0]?.toUpperCase() || '')
  return letters.join('') || 'DR'
}

export function openSlotsFor(availability, doctorId) {
  const row = (availability || []).find((item) => String(item.doctor_id) === String(doctorId))
  return row?.available_slots?.length || 0
}

export function totalOpenSlots(availability) {
  return (availability || []).reduce(
    (sum, item) => sum + (item.available_slots?.length || 0),
    0,
  )
}
