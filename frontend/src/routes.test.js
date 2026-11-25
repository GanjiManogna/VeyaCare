import assert from 'node:assert/strict'
import test from 'node:test'
import { pageFromLocation, PAGE_ROUTES, PAGES, routeUrl } from './routes.js'

test('availability and appointment management have distinct direct routes', () => {
  assert.equal(pageFromLocation('/availability'), PAGES.AVAILABILITY)
  assert.equal(pageFromLocation('/my-appointments'), PAGES.APPOINTMENTS)
  assert.notEqual(PAGE_ROUTES[PAGES.AVAILABILITY], PAGE_ROUTES[PAGES.APPOINTMENTS])
})

test('all known pages restore from their direct URL, including a trailing slash', () => {
  for (const [page, path] of Object.entries(PAGE_ROUTES)) {
    assert.equal(pageFromLocation(path), page)
    if (path !== '/') assert.equal(pageFromLocation(`${path}/`), page)
  }
})

test('availability routes preserve speciality filters in the URL', () => {
  assert.equal(
    routeUrl(PAGES.AVAILABILITY, { speciality: 'General Medicine', date: '2026-11-26' }),
    '/availability?speciality=General+Medicine&date=2026-11-26',
  )
})
