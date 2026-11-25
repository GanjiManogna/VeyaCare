import test from 'node:test'
import assert from 'node:assert/strict'
import { openSlotsFor, totalOpenSlots } from './format.js'

test('slot lookup matches doctor identifiers returned as numbers or strings', () => {
  const availability = [{ doctor_id: 12, available_slots: [{ slot_id: 1 }, { slot_id: 2 }] }]

  assert.equal(openSlotsFor(availability, 12), 2)
  assert.equal(openSlotsFor(availability, '12'), 2)
  assert.equal(totalOpenSlots(availability), 2)
})
