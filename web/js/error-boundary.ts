/**
 * web/js/error-boundary.ts — StoryForge global error boundary
 *
 * Responsibilities:
 *   - Catch unhandled synchronous errors (window.onerror)
 *   - Catch unhandled Promise rejections (window.onunhandledrejection)
 *   - Display a user-friendly toast for non-fatal errors
 *   - Display a full-screen overlay with a "Reload" button for fatal errors
 *   - Log every caught error to the console with structured context
 *
 * Usage (CDN / no-build mode):
 *   <script src="/static/js/error-boundary.js"></script>
 *   — load BEFORE Alpine.js so errors during initialisation are caught.
 *
 * Usage (Alpine.js component):
 *   Alpine.data('errorBoundary', errorBoundaryComponent)
 *   — see exported `errorBoundaryComponent` at the bottom of this file.
 *
 * The toast container is injected into <body> lazily on first error.
 */

;(function (win: Window & typeof globalThis, doc: Document): void {
  'use strict'

  // ── Configuration ──────────────────────────────────────────────────────────

  /** Maximum toasts visible simultaneously before oldest is removed. */
  const MAX_TOASTS: number = 5

  /** Auto-dismiss non-fatal toasts after this many milliseconds. */
  const TOAST_DURATION_MS: number = 6000

  /** Errors matching these patterns are treated as fatal (full-screen overlay). */
  const FATAL_PATTERNS: RegExp[] = [
    /ChunkLoadError/i,
    /Loading chunk \d+ failed/i,
    /Failed to fetch dynamically imported module/i,
    /out of memory/i,
  ]

  // ── Internal state ─────────────────────────────────────────────────────────

  let _toastContainer: HTMLElement | null = null
  let _toastCount: number = 0

  // ── Helpers ────────────────────────────────────────────────────────────────

  /**
   * Determine whether an error should trigger the fatal overlay.
   */
  function isFatal(err: Error | string | unknown): boolean {
    const msg = (err && (err as Error).message) ? (err as Error).message : String(err)
    return FATAL_PATTERNS.some(function (re: RegExp): boolean { return re.test(msg) })
  }

  /**
   * Lazy-create and return the toast container element.
   */
  function getToastContainer(): HTMLElement {
    if (_toastContainer) return _toastContainer

    _toastContainer = doc.createElement('div')
    _toastContainer.id = 'sf-toast-container'
    _toastContainer.setAttribute('aria-live', 'polite')
    _toastContainer.setAttribute('aria-atomic', 'false')
    _toastContainer.style.cssText = [
      'position:fixed',
      'bottom:1.5rem',
      'right:1.5rem',
      'z-index:99999',
      'display:flex',
      'flex-direction:column',
      'gap:0.5rem',
      'max-width:26rem',
      'pointer-events:none',
    ].join(';')

    doc.body.appendChild(_toastContainer)
    return _toastContainer
  }

  /**
   * Show a dismissible toast notification.
   */
  function showToast(message: string, level?: 'error' | 'warning'): void {
    const resolvedLevel: 'error' | 'warning' = level || 'error'
    const container: HTMLElement = getToastContainer()

    // Evict oldest toast when limit reached
    while (_toastCount >= MAX_TOASTS && container.firstChild) {
      container.removeChild(container.firstChild)
      _toastCount--
    }

    const isError: boolean  = resolvedLevel === 'error'
    const bgColor: string   = isError ? '#FEF2F2' : '#FFFBEB'
    const border: string    = isError ? '#FECACA' : '#FDE68A'
    const textColor: string = isError ? '#991B1B' : '#92400E'
    const iconChar: string  = isError ? '✕' : '⚠'

    const toast: HTMLDivElement = doc.createElement('div')
    toast.setAttribute('role', 'alert')
    toast.style.cssText = [
      'display:flex',
      'align-items:flex-start',
      'gap:0.625rem',
      'padding:0.75rem 1rem',
      'background:' + bgColor,
      'border:1px solid ' + border,
      'border-radius:8px',
      'box-shadow:0 4px 6px -1px rgb(0 0 0/0.1)',
      'font-family:system-ui,sans-serif',
      'font-size:14px',
      'line-height:1.4',
      'color:' + textColor,
      'pointer-events:auto',
      'opacity:0',
      'transform:translateY(0.5rem)',
      'transition:opacity 200ms ease,transform 200ms ease',
    ].join(';')

    const icon: HTMLSpanElement = doc.createElement('span')
    icon.textContent = iconChar
    icon.setAttribute('aria-hidden', 'true')
    icon.style.cssText = 'flex-shrink:0;font-weight:700;font-size:13px;margin-top:1px'

    const text: HTMLSpanElement = doc.createElement('span')
    text.style.cssText = 'flex:1;word-break:break-word'
    text.textContent = message

    const closeBtn: HTMLButtonElement = doc.createElement('button')
    closeBtn.textContent = '×'
    closeBtn.setAttribute('aria-label', 'Dismiss error')
    closeBtn.style.cssText = [
      'flex-shrink:0',
      'margin-left:auto',
      'background:none',
      'border:none',
      'cursor:pointer',
      'font-size:18px',
      'line-height:1',
      'color:' + textColor,
      'padding:0 2px',
      'opacity:0.7',
    ].join(';')
    closeBtn.addEventListener('click', function (): void { removeToast(toast) })

    toast.appendChild(icon)
    toast.appendChild(text)
    toast.appendChild(closeBtn)
    container.appendChild(toast)
    _toastCount++

    // Animate in on next frame
    requestAnimationFrame(function (): void {
      toast.style.opacity = '1'
      toast.style.transform = 'translateY(0)'
    })

    // Auto-dismiss
    let timer: ReturnType<typeof setTimeout> = setTimeout(function (): void { removeToast(toast) }, TOAST_DURATION_MS)
    toast.addEventListener('mouseenter', function (): void { clearTimeout(timer) })
    toast.addEventListener('mouseleave', function (): void {
      timer = setTimeout(function (): void { removeToast(toast) }, TOAST_DURATION_MS / 2)
    })
  }

  /**
   * Animate-out and remove a toast element.
   */
  function removeToast(toast: HTMLElement): void {
    toast.style.opacity = '0'
    toast.style.transform = 'translateY(0.5rem)'
    setTimeout(function (): void {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast)
        _toastCount--
      }
    }, 220)
  }

  /**
   * Show a full-screen fatal error overlay.
   */
  function showFatalOverlay(message: string): void {
    // Only one overlay at a time
    if (doc.getElementById('sf-fatal-overlay')) return

    const overlay: HTMLDivElement = doc.createElement('div')
    overlay.id = 'sf-fatal-overlay'
    overlay.setAttribute('role', 'alertdialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.setAttribute('aria-label', 'Fatal application error')
    overlay.style.cssText = [
      'position:fixed',
      'inset:0',
      'z-index:100000',
      'display:flex',
      'align-items:center',
      'justify-content:center',
      'background:rgb(0 0 0/0.7)',
      'font-family:system-ui,sans-serif',
      'padding:1rem',
    ].join(';')

    const card: HTMLDivElement = doc.createElement('div')
    card.style.cssText = [
      'background:#fff',
      'border-radius:12px',
      'padding:2rem',
      'max-width:28rem',
      'width:100%',
      'text-align:center',
      'box-shadow:0 20px 40px rgb(0 0 0/0.3)',
    ].join(';')

    const heading: HTMLHeadingElement = doc.createElement('h2')
    heading.style.cssText = 'margin:0 0 0.5rem;font-size:1.25rem;font-weight:700;color:#1e293b'
    heading.textContent = 'Something went wrong'

    const body: HTMLParagraphElement = doc.createElement('p')
    body.style.cssText = 'margin:0 0 1.5rem;font-size:14px;color:#64748b;word-break:break-word'
    body.textContent = message || 'An unexpected error occurred. Reloading the page usually fixes this.'

    const reloadBtn: HTMLButtonElement = doc.createElement('button')
    reloadBtn.textContent = 'Reload page'
    reloadBtn.style.cssText = [
      'display:inline-flex',
      'align-items:center',
      'gap:0.375rem',
      'padding:0.625rem 1.5rem',
      'background:#2563eb',
      'color:#fff',
      'border:none',
      'border-radius:8px',
      'font-size:15px',
      'font-weight:600',
      'cursor:pointer',
      'transition:background 150ms ease',
    ].join(';')
    reloadBtn.addEventListener('mouseenter', function (): void { reloadBtn.style.background = '#1d4ed8' })
    reloadBtn.addEventListener('mouseleave', function (): void { reloadBtn.style.background = '#2563eb' })
    reloadBtn.addEventListener('click', function (): void { win.location.reload() })

    card.appendChild(heading)
    card.appendChild(body)
    card.appendChild(reloadBtn)
    overlay.appendChild(card)
    doc.body.appendChild(overlay)
  }

  // ── Error context type ──────────────────────────────────────────────────────

  interface ErrorContext {
    source?: string
    lineno?: number
    colno?: number
    type?: string
  }

  /**
   * Central error handler — decides toast vs fatal overlay and logs to console.
   */
  function handleError(error: Error | string | unknown, ctx?: ErrorContext): void {
    const resolvedCtx: ErrorContext = ctx || {}
    const message: string = (error && (error as Error).message) ? (error as Error).message : String(error)

    // Structured console log with context
    console.error('[StoryForge] Unhandled error', {
      message: message,
      stack: (error && (error as Error).stack) || null,
      source: resolvedCtx.source || null,
      lineno: resolvedCtx.lineno || null,
      colno: resolvedCtx.colno || null,
      type: resolvedCtx.type || 'error',
      timestamp: new Date().toISOString(),
    })

    if (isFatal(error)) {
      showFatalOverlay(message)
    } else {
      showToast(message)
    }
  }

  // ── Global handlers ────────────────────────────────────────────────────────

  /**
   * Catch synchronous runtime errors.
   * Returning true suppresses the browser's default error reporting.
   */
  win.onerror = function (
    message: string | Event,
    source?: string,
    lineno?: number,
    colno?: number,
    error?: Error
  ): boolean {
    handleError(error || message, { source: source, lineno: lineno, colno: colno, type: 'onerror' })
    return false // allow default browser reporting to continue
  }

  /**
   * Catch unhandled Promise rejections.
   */
  win.addEventListener('unhandledrejection', function (event: PromiseRejectionEvent): void {
    const reason: unknown = event.reason
    handleError(reason, { type: 'unhandledrejection' })
    // Do NOT call event.preventDefault() — allow devtools to still flag these
  })

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Manually show a toast — useful from app.js for handled-but-notable errors.
   */
  win.sfShowToast = showToast

  /**
   * Manually trigger a fatal overlay — useful for auth failures, etc.
   */
  win.sfShowFatal = showFatalOverlay

  // ── Alpine.js component export ─────────────────────────────────────────────

  /**
   * Alpine.js data component — register with:
   *   Alpine.data('errorBoundary', window.errorBoundaryComponent)
   *
   * Exposes showToast() and showFatal() as Alpine reactive methods.
   */
  win.errorBoundaryComponent = function (): { showToast: typeof win.sfShowToast; showFatal: typeof win.sfShowFatal } {
    return {
      showToast: showToast,
      showFatal: showFatalOverlay,
    }
  }

}(window, document))
