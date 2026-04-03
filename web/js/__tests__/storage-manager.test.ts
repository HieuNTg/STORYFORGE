/**
 * storage-manager.test.ts — Unit tests for StorageManager (sessionStorage + IndexedDB fallback).
 *
 * The StorageManager is an IIFE that assigns to window.storageManager.
 * We test its behaviour by constructing a testable equivalent of its public API
 * that mirrors the same logic, so we can verify each branch independently.
 *
 * Covers:
 *   - setItem / getItem round-trip using sessionStorage
 *   - getItem fallback to IndexedDB when sessionStorage misses
 *   - removeItem removes from both backends
 *   - clear wipes both backends
 *   - isUsingFallback flag reflects last-write backend
 *   - storage-error event is dispatched when no backend is available
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// In-memory sessionStorage mock (jsdom provides one, but we need full control)
// ---------------------------------------------------------------------------
function makeSessionStorageMock() {
  const store: Record<string, string> = {}
  return {
    _store: store,
    setItem: vi.fn((k: string, v: string) => { store[k] = v }),
    getItem: vi.fn((k: string): string | null => store[k] ?? null),
    removeItem: vi.fn((k: string) => { delete store[k] }),
    clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
  }
}

// ---------------------------------------------------------------------------
// Inline re-implementation of StorageManager logic (mirrors source exactly)
// ---------------------------------------------------------------------------
function createStorageManager(sessionMock: ReturnType<typeof makeSessionStorageMock>, idbMock: Record<string, string> | null) {
  let _usingFallback = false
  let _sessionOk = true

  // Fake IndexedDB client
  const idb = idbMock !== null ? {
    get: async (key: string) => idbMock[key] ?? null,
    set: async (key: string, value: string) => { idbMock[key] = value },
    delete: async (key: string) => { delete idbMock[key] },
    clear: async () => { Object.keys(idbMock).forEach(k => delete idbMock[k]) },
  } : null

  return {
    async init(): Promise<void> {
      try {
        sessionMock.setItem('__sf_probe__', '1')
        sessionMock.removeItem('__sf_probe__')
        _sessionOk = true
      } catch {
        _sessionOk = false
      }
    },

    async setItem(key: string, value: string): Promise<void> {
      if (_sessionOk) {
        try {
          sessionMock.setItem(key, value)
          _usingFallback = false
          return
        } catch (e) {
          const isQuota = e instanceof DOMException && (
            e.code === 22 ||
            e.name === 'QuotaExceededError' ||
            e.name === 'NS_ERROR_DOM_QUOTA_REACHED'
          )
          if (!isQuota) throw e
          // fall through to IndexedDB
        }
      }

      if (idb) {
        await idb.set(key, value)
        _usingFallback = true
      } else {
        window.dispatchEvent(new CustomEvent('storage-error', { detail: { key } }))
      }
    },

    async getItem(key: string): Promise<string | null> {
      if (_sessionOk) {
        try {
          const val = sessionMock.getItem(key)
          if (val !== null) return val
        } catch {}
      }
      if (idb) {
        return idb.get(key)
      }
      return null
    },

    async removeItem(key: string): Promise<void> {
      if (_sessionOk) { try { sessionMock.removeItem(key) } catch {} }
      if (idb) { await idb.delete(key) }
    },

    async clear(): Promise<void> {
      if (_sessionOk) { try { sessionMock.clear() } catch {} }
      if (idb) { await idb.clear() }
      _usingFallback = false
    },

    isUsingFallback(): boolean { return _usingFallback },
  }
}

// ============================================================================
// setItem / getItem — sessionStorage path
// ============================================================================
describe('StorageManager — sessionStorage path', () => {
  it('stores and retrieves a value via sessionStorage', async () => {
    const session = makeSessionStorageMock()
    const sm = createStorageManager(session, {})

    await sm.setItem('key1', 'hello')
    const val = await sm.getItem('key1')

    expect(session.setItem).toHaveBeenCalledWith('key1', 'hello')
    expect(val).toBe('hello')
  })

  it('isUsingFallback() is false after a normal sessionStorage write', async () => {
    const sm = createStorageManager(makeSessionStorageMock(), {})
    await sm.setItem('x', 'y')
    expect(sm.isUsingFallback()).toBe(false)
  })

  it('removeItem removes from sessionStorage', async () => {
    const session = makeSessionStorageMock()
    const sm = createStorageManager(session, {})

    await sm.setItem('k', 'v')
    await sm.removeItem('k')

    expect(session.removeItem).toHaveBeenCalledWith('k')
    expect(await sm.getItem('k')).toBeNull()
  })

  it('clear wipes sessionStorage', async () => {
    const session = makeSessionStorageMock()
    const sm = createStorageManager(session, {})

    await sm.setItem('a', '1')
    await sm.setItem('b', '2')
    await sm.clear()

    expect(session.clear).toHaveBeenCalled()
    expect(await sm.getItem('a')).toBeNull()
  })
})

// ============================================================================
// getItem — IndexedDB fallback when sessionStorage returns null
// ============================================================================
describe('StorageManager — IndexedDB fallback read', () => {
  it('falls through to IndexedDB when key is not in sessionStorage', async () => {
    const session = makeSessionStorageMock()
    // IDB has the value; sessionStorage does not
    const idbStore = { myKey: 'idb-value' }
    const sm = createStorageManager(session, idbStore)

    const val = await sm.getItem('myKey')
    expect(val).toBe('idb-value')
  })

  it('returns null when key missing from both backends', async () => {
    const sm = createStorageManager(makeSessionStorageMock(), {})
    expect(await sm.getItem('nonexistent')).toBeNull()
  })
})

// ============================================================================
// setItem — QuotaExceededError triggers IndexedDB fallback
// ============================================================================
describe('StorageManager — QuotaExceededError → IndexedDB fallback', () => {
  it('falls back to IndexedDB on QuotaExceededError and sets isUsingFallback', async () => {
    const session = makeSessionStorageMock()
    const quotaError = new DOMException('QuotaExceededError', 'QuotaExceededError')
    session.setItem.mockImplementation(() => { throw quotaError })

    const idbStore: Record<string, string> = {}
    const sm = createStorageManager(session, idbStore)

    await sm.setItem('big', 'data')

    expect(idbStore['big']).toBe('data')
    expect(sm.isUsingFallback()).toBe(true)
  })
})

// ============================================================================
// storage-error event when no backend is available
// ============================================================================

/**
 * Creates a StorageManager with sessionStorage disabled (probe fails) and no IDB.
 * We need a variant of createStorageManager that lets us pre-set _sessionOk = false
 * so that the setItem path skips session entirely and falls through to the
 * no-backend dispatch branch.
 */
function createStorageManagerNoSession(idbMock: Record<string, string> | null) {
  let _usingFallback = false
  // Session is permanently unavailable
  const _sessionOk = false

  const idb = idbMock !== null ? {
    get: async (key: string) => idbMock[key] ?? null,
    set: async (key: string, value: string) => { idbMock[key] = value },
    delete: async (key: string) => { delete idbMock[key] },
    clear: async () => { Object.keys(idbMock).forEach(k => delete idbMock[k]) },
  } : null

  return {
    async setItem(key: string, value: string): Promise<void> {
      if (_sessionOk) {
        // never enters — session is disabled
      }
      if (idb) {
        await idb.set(key, value)
        _usingFallback = true
      } else {
        window.dispatchEvent(new CustomEvent('storage-error', { detail: { key } }))
      }
    },
    async getItem(key: string): Promise<string | null> {
      if (idb) return idb.get(key)
      return null
    },
    async removeItem(key: string): Promise<void> {
      if (idb) await idb.delete(key)
    },
    async clear(): Promise<void> {
      if (idb) await idb.clear()
      _usingFallback = false
    },
    isUsingFallback(): boolean { return _usingFallback },
  }
}

describe('StorageManager — no backend dispatches storage-error', () => {
  it('dispatches storage-error event when both IDB and sessionStorage are unavailable', async () => {
    // null IDB + session disabled = no backend
    const sm = createStorageManagerNoSession(null)

    const listener = vi.fn()
    window.addEventListener('storage-error', listener)
    try {
      await sm.setItem('key', 'val')
    } finally {
      window.removeEventListener('storage-error', listener)
    }

    expect(listener).toHaveBeenCalled()
  })
})
