/**
 * setup.js — Vitest global test setup
 *
 * Runs before every test file. Resets fetch mocks and provides
 * lightweight Alpine.js stubs so component logic can be tested
 * without a full browser environment.
 */

import { vi, beforeEach, afterEach } from 'vitest'

// ── Fetch mock ──────────────────────────────────────────────────────────────
// jsdom does not implement fetch; we provide a vi.fn() stub here so individual
// tests can configure it with vi.mocked(fetch).mockResolvedValueOnce(...).
if (!globalThis.fetch) {
  globalThis.fetch = vi.fn()
}

beforeEach(() => {
  // Reset fetch between tests so mock state never leaks
  vi.resetAllMocks()
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Minimal Alpine.js shim ──────────────────────────────────────────────────
// Alpine is loaded from CDN in production; unit tests don't need the full
// library. Components that call Alpine.store() / Alpine.data() are tested
// at the JS-logic level only (no DOM rendering).
globalThis.Alpine = {
  store: vi.fn(),
  data: vi.fn(),
  start: vi.fn(),
}
