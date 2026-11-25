import assert from 'node:assert/strict'
import test from 'node:test'
import {
  clearSavedPatientPhone,
  appointmentsForPatient,
  appointmentStatusLabel,
  redactPhoneText,
  PATIENT_PHONE_KEY,
  readSavedPatientPhone,
  saveConfirmedPatientPhone,
} from './patientLookup.js'

function createStorage() {
  const values = new Map()
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  }
}

test('valid confirmed patient number can be saved and loaded as a device lookup preference', () => {
  const storage = createStorage()
  assert.equal(readSavedPatientPhone(storage), '')
  assert.equal(saveConfirmedPatientPhone('9123456789', storage), true)
  assert.equal(storage.getItem(PATIENT_PHONE_KEY), '9123456789')
  assert.equal(readSavedPatientPhone(storage), '9123456789')
})

test('invalid phone values cannot replace a saved patient lookup number', () => {
  const storage = createStorage()
  saveConfirmedPatientPhone('9123456789', storage)
  assert.equal(saveConfirmedPatientPhone('91912345678', storage), false)
  assert.equal(saveConfirmedPatientPhone('5123456789', storage), false)
  assert.equal(saveConfirmedPatientPhone('9123456789\n', storage), false)
  assert.equal(readSavedPatientPhone(storage), '9123456789')
})

test('switching or clearing the saved phone changes the lookup key without retaining the prior value', () => {
  const storage = createStorage()
  saveConfirmedPatientPhone('9123456789', storage)
  saveConfirmedPatientPhone('8123456789', storage)
  assert.equal(readSavedPatientPhone(storage), '8123456789')
  assert.equal(clearSavedPatientPhone(storage), true)
  assert.equal(readSavedPatientPhone(storage), '')
})

test('patient appointments retain booked and cancelled history but never include another phone number', () => {
  const rows = [
    { id: 1, phone_number: '9123456789', status: 'booked' },
    { id: 2, phone_number: '9123456789', status: 'cancelled' },
    { id: 3, phone_number: '8123456789', status: 'booked' },
  ]
  const patientRows = appointmentsForPatient(rows, '9123456789')
  assert.deepEqual(patientRows.map((row) => row.status), ['booked', 'cancelled'])
  assert.deepEqual(appointmentsForPatient(rows, '8123456789').map((row) => row.id), [3])
  assert.deepEqual(appointmentsForPatient(rows, ''), [])
  assert.equal(appointmentStatusLabel('booked'), 'Booked')
  assert.equal(appointmentStatusLabel('cancelled'), 'Cancelled')
})

test('full phone numbers are masked in voice text, including digit-separated speech text', () => {
  assert.equal(redactPhoneText('Your number is 9123456789.'), 'Your number is ••••••••••.')
  assert.equal(redactPhoneText('I heard 9 1 2 3 4 5 6 7 8 9.'), 'I heard ••••••••••.')
})

test('storage access failures safely produce no saved lookup', () => {
  const inaccessibleStorage = {
    getItem() { throw new Error('blocked') },
    setItem() { throw new Error('blocked') },
    removeItem() { throw new Error('blocked') },
  }
  assert.equal(readSavedPatientPhone(inaccessibleStorage), '')
  assert.equal(saveConfirmedPatientPhone('9123456789', inaccessibleStorage), false)
  assert.equal(clearSavedPatientPhone(inaccessibleStorage), false)
})
