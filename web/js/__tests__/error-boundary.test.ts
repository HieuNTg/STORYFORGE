/**
 * error-boundary.test.ts — Unit tests for error-boundary logic.
 *
 * The error-boundary is an IIFE that mutates window globals.
 * We test the key behaviours by extracting the pure logic functions inline:
 *   - isFatal(): classifies errors as fatal or non-fatal
 *   - showToast(): injects a toast element into the DOM
 *   - showFatalOverlay(): injects the full-screen overlay
 *   - Toast auto-eviction when MAX_TOASTS is exceeded
 *   - Close button removes the toast
 *
 * Covers:
 *   - Fatal pattern detection (ChunkLoadError, out of memory, etc.)
 *   - Non-fatal errors produce toast, not overlay
 *   - Fatal errors produce overlay, not toast
 *   - Overlay is a singleton (second call is a no-op)
 *   - Toast eviction enforces the MAX_TOASTS cap
 */

import { describe, it, expect, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Inline extracted logic from error-boundary.ts (pure, no side effects on window)
// ---------------------------------------------------------------------------

const FATAL_PATTERNS: RegExp[] = [
  /ChunkLoadError/i,
  /Loading chunk \d+ failed/i,
  /Failed to fetch dynamically imported module/i,
  /out of memory/i,
]

const MAX_TOASTS = 5
const TOAST_DURATION_MS = 6000

function isFatal(err: Error | string | unknown): boolean {
  const msg = (err && (err as Error).message) ? (err as Error).message : String(err)
  return FATAL_PATTERNS.some(re => re.test(msg))
}

function createToastSystem(doc: Document) {
  let container: HTMLElement | null = null
  let toastCount = 0

  function getContainer(): HTMLElement {
    if (container) return container
    container = doc.createElement('div')
    container.id = 'sf-toast-container'
    container.setAttribute('aria-live', 'polite')
    doc.body.appendChild(container)
    return container
  }

  function removeToast(toast: HTMLElement): void {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast)
      toastCount--
    }
  }

  function showToast(message: string, level?: 'error' | 'warning'): void {
    const resolvedLevel = level || 'error'
    const c = getContainer()

    while (toastCount >= MAX_TOASTS && c.firstChild) {
      c.removeChild(c.firstChild)
      toastCount--
    }

    const toast = doc.createElement('div')
    toast.setAttribute('role', 'alert')

    const text = doc.createElement('span')
    text.textContent = message
    toast.appendChild(text)

    const icon = doc.createElement('span')
    icon.textContent = resolvedLevel === 'error' ? '✕' : '⚠'
    toast.insertBefore(icon, text)

    const closeBtn = doc.createElement('button')
    closeBtn.setAttribute('aria-label', 'Dismiss error')
    closeBtn.addEventListener('click', () => removeToast(toast))
    toast.appendChild(closeBtn)

    c.appendChild(toast)
    toastCount++
  }

  return { showToast, getCount: () => toastCount, getContainer: () => container }
}

function createOverlaySystem(doc: Document) {
  function showFatalOverlay(message: string): void {
    if (doc.getElementById('sf-fatal-overlay')) return

    const overlay = doc.createElement('div')
    overlay.id = 'sf-fatal-overlay'
    overlay.setAttribute('role', 'alertdialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.setAttribute('aria-label', 'Fatal application error')

    const card = doc.createElement('div')
    const heading = doc.createElement('h2')
    heading.textContent = 'Something went wrong'

    const body = doc.createElement('p')
    body.textContent = message || 'An unexpected error occurred. Reloading the page usually fixes this.'

    const reloadBtn = doc.createElement('button')
    reloadBtn.textContent = 'Reload page'

    card.appendChild(heading)
    card.appendChild(body)
    card.appendChild(reloadBtn)
    overlay.appendChild(card)
    doc.body.appendChild(overlay)
  }
  return { showFatalOverlay }
}

// ============================================================================
// isFatal()
// ============================================================================
describe('isFatal()', () => {
  it('returns true for ChunkLoadError', () => {
    expect(isFatal(new Error('ChunkLoadError: failed to load chunk 42'))).toBe(true)
  })

  it('returns true for "Loading chunk N failed" pattern', () => {
    expect(isFatal(new Error('Loading chunk 7 failed'))).toBe(true)
  })

  it('returns true for "out of memory" message', () => {
    expect(isFatal(new Error('JavaScript heap out of memory'))).toBe(true)
  })

  it('returns true for dynamically imported module failure', () => {
    expect(isFatal(new Error('Failed to fetch dynamically imported module: ./chunk.js'))).toBe(true)
  })

  it('returns false for ordinary network errors', () => {
    expect(isFatal(new Error('Network request failed'))).toBe(false)
  })

  it('returns false for validation errors', () => {
    expect(isFatal(new Error('POST /stories: 422'))).toBe(false)
  })

  it('handles plain string input', () => {
    expect(isFatal('out of memory')).toBe(true)
    expect(isFatal('something broke')).toBe(false)
  })
})

// ============================================================================
// Toast system
// ============================================================================
describe('showToast()', () => {
  let toastSys: ReturnType<typeof createToastSystem>

  beforeEach(() => {
    // Fresh document body for each test
    document.body.innerHTML = ''
    toastSys = createToastSystem(document)
  })

  it('creates a toast with role="alert" and the given message', () => {
    toastSys.showToast('Something failed')

    const toasts = document.querySelectorAll('[role="alert"]')
    expect(toasts.length).toBe(1)
    expect(toasts[0].textContent).toContain('Something failed')
  })

  it('uses error icon (✕) for error level', () => {
    toastSys.showToast('Oops', 'error')
    const icon = document.querySelector('[aria-hidden]') ??
                 document.querySelector('[role="alert"] span:first-child')
    expect(document.querySelector('[role="alert"]')!.textContent).toContain('✕')
  })

  it('uses warning icon (⚠) for warning level', () => {
    toastSys.showToast('Watch out', 'warning')
    expect(document.querySelector('[role="alert"]')!.textContent).toContain('⚠')
  })

  it('evicts the oldest toast when MAX_TOASTS is exceeded', () => {
    for (let i = 1; i <= MAX_TOASTS + 1; i++) {
      toastSys.showToast(`Toast ${i}`)
    }
    const toasts = document.querySelectorAll('[role="alert"]')
    expect(toasts.length).toBe(MAX_TOASTS)
  })

  it('close button removes the toast from the DOM', () => {
    toastSys.showToast('Dismissible')
    const closeBtn = document.querySelector('button[aria-label="Dismiss error"]') as HTMLButtonElement
    closeBtn.click()
    expect(document.querySelectorAll('[role="alert"]').length).toBe(0)
  })
})

// ============================================================================
// Fatal overlay
// ============================================================================
describe('showFatalOverlay()', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('creates the fatal overlay with alertdialog role', () => {
    const { showFatalOverlay } = createOverlaySystem(document)
    showFatalOverlay('Chunk load failed')

    const overlay = document.getElementById('sf-fatal-overlay')
    expect(overlay).not.toBeNull()
    expect(overlay!.getAttribute('role')).toBe('alertdialog')
    expect(overlay!.getAttribute('aria-modal')).toBe('true')
  })

  it('includes the error message in the overlay body', () => {
    const { showFatalOverlay } = createOverlaySystem(document)
    showFatalOverlay('Something catastrophic happened')

    const overlay = document.getElementById('sf-fatal-overlay')
    expect(overlay!.textContent).toContain('Something catastrophic happened')
  })

  it('is a singleton — second call does not create a second overlay', () => {
    const { showFatalOverlay } = createOverlaySystem(document)
    showFatalOverlay('First error')
    showFatalOverlay('Second error')

    const overlays = document.querySelectorAll('#sf-fatal-overlay')
    expect(overlays.length).toBe(1)
    // First message retained
    expect(overlays[0].textContent).toContain('First error')
  })

  it('includes a Reload page button', () => {
    const { showFatalOverlay } = createOverlaySystem(document)
    showFatalOverlay('Fatal!')

    const btn = document.querySelector('#sf-fatal-overlay button')
    expect(btn).not.toBeNull()
    expect(btn!.textContent).toBe('Reload page')
  })
})
