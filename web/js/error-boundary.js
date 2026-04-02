/**
 * web/js/error-boundary.js — StoryForge global error boundary
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

;(function (window, document) {
  'use strict'

  // ── Configuration ──────────────────────────────────────────────────────────

  /** Maximum toasts visible simultaneously before oldest is removed. */
  var MAX_TOASTS = 5

  /** Auto-dismiss non-fatal toasts after this many milliseconds. */
  var TOAST_DURATION_MS = 6000

  /** Errors matching these patterns are treated as fatal (full-screen overlay). */
  var FATAL_PATTERNS = [
    /ChunkLoadError/i,
    /Loading chunk \d+ failed/i,
    /Failed to fetch dynamically imported module/i,
    /out of memory/i,
  ]

  // ── Internal state ─────────────────────────────────────────────────────────

  var _toastContainer = null
  var _toastCount = 0

  // ── Helpers ────────────────────────────────────────────────────────────────

  /**
   * Determine whether an error should trigger the fatal overlay.
   * @param {Error|string} err
   * @returns {boolean}
   */
  function isFatal(err) {
    var msg = (err && err.message) ? err.message : String(err)
    return FATAL_PATTERNS.some(function (re) { return re.test(msg) })
  }

  /**
   * Lazy-create and return the toast container element.
   * @returns {HTMLElement}
   */
  function getToastContainer() {
    if (_toastContainer) return _toastContainer

    _toastContainer = document.createElement('div')
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

    document.body.appendChild(_toastContainer)
    return _toastContainer
  }

  /**
   * Show a dismissible toast notification.
   * @param {string} message  Human-readable message.
   * @param {'error'|'warning'} [level='error']
   */
  function showToast(message, level) {
    level = level || 'error'
    var container = getToastContainer()

    // Evict oldest toast when limit reached
    while (_toastCount >= MAX_TOASTS && container.firstChild) {
      container.removeChild(container.firstChild)
      _toastCount--
    }

    var isError = level === 'error'
    var bgColor  = isError ? '#FEF2F2' : '#FFFBEB'
    var border   = isError ? '#FECACA' : '#FDE68A'
    var textColor = isError ? '#991B1B' : '#92400E'
    var iconChar = isError ? '✕' : '⚠'

    var toast = document.createElement('div')
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

    var icon = document.createElement('span')
    icon.textContent = iconChar
    icon.setAttribute('aria-hidden', 'true')
    icon.style.cssText = 'flex-shrink:0;font-weight:700;font-size:13px;margin-top:1px'

    var text = document.createElement('span')
    text.style.cssText = 'flex:1;word-break:break-word'
    text.textContent = message

    var closeBtn = document.createElement('button')
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
    closeBtn.addEventListener('click', function () { removeToast(toast) })

    toast.appendChild(icon)
    toast.appendChild(text)
    toast.appendChild(closeBtn)
    container.appendChild(toast)
    _toastCount++

    // Animate in on next frame
    requestAnimationFrame(function () {
      toast.style.opacity = '1'
      toast.style.transform = 'translateY(0)'
    })

    // Auto-dismiss
    var timer = setTimeout(function () { removeToast(toast) }, TOAST_DURATION_MS)
    toast.addEventListener('mouseenter', function () { clearTimeout(timer) })
    toast.addEventListener('mouseleave', function () {
      timer = setTimeout(function () { removeToast(toast) }, TOAST_DURATION_MS / 2)
    })
  }

  /**
   * Animate-out and remove a toast element.
   * @param {HTMLElement} toast
   */
  function removeToast(toast) {
    toast.style.opacity = '0'
    toast.style.transform = 'translateY(0.5rem)'
    setTimeout(function () {
      if (toast.parentNode) {
        toast.parentNode.removeChild(toast)
        _toastCount--
      }
    }, 220)
  }

  /**
   * Show a full-screen fatal error overlay.
   * @param {string} message
   */
  function showFatalOverlay(message) {
    // Only one overlay at a time
    if (document.getElementById('sf-fatal-overlay')) return

    var overlay = document.createElement('div')
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

    var card = document.createElement('div')
    card.style.cssText = [
      'background:#fff',
      'border-radius:12px',
      'padding:2rem',
      'max-width:28rem',
      'width:100%',
      'text-align:center',
      'box-shadow:0 20px 40px rgb(0 0 0/0.3)',
    ].join(';')

    var heading = document.createElement('h2')
    heading.style.cssText = 'margin:0 0 0.5rem;font-size:1.25rem;font-weight:700;color:#1e293b'
    heading.textContent = 'Something went wrong'

    var body = document.createElement('p')
    body.style.cssText = 'margin:0 0 1.5rem;font-size:14px;color:#64748b;word-break:break-word'
    body.textContent = message || 'An unexpected error occurred. Reloading the page usually fixes this.'

    var reloadBtn = document.createElement('button')
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
    reloadBtn.addEventListener('mouseenter', function () { reloadBtn.style.background = '#1d4ed8' })
    reloadBtn.addEventListener('mouseleave', function () { reloadBtn.style.background = '#2563eb' })
    reloadBtn.addEventListener('click', function () { window.location.reload() })

    card.appendChild(heading)
    card.appendChild(body)
    card.appendChild(reloadBtn)
    overlay.appendChild(card)
    document.body.appendChild(overlay)
  }

  /**
   * Central error handler — decides toast vs fatal overlay and logs to console.
   * @param {Error|string} error
   * @param {{ source?: string, lineno?: number, colno?: number, type?: string }} [ctx]
   */
  function handleError(error, ctx) {
    ctx = ctx || {}
    var message = (error && error.message) ? error.message : String(error)

    // Structured console log with context
    console.error('[StoryForge] Unhandled error', {
      message: message,
      stack: (error && error.stack) || null,
      source: ctx.source || null,
      lineno: ctx.lineno || null,
      colno: ctx.colno || null,
      type: ctx.type || 'error',
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
  window.onerror = function (message, source, lineno, colno, error) {
    handleError(error || message, { source: source, lineno: lineno, colno: colno, type: 'onerror' })
    return false // allow default browser reporting to continue
  }

  /**
   * Catch unhandled Promise rejections.
   */
  window.addEventListener('unhandledrejection', function (event) {
    var reason = event.reason
    handleError(reason, { type: 'unhandledrejection' })
    // Do NOT call event.preventDefault() — allow devtools to still flag these
  })

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Manually show a toast — useful from app.js for handled-but-notable errors.
   * @param {string} message
   * @param {'error'|'warning'} [level]
   */
  window.sfShowToast = showToast

  /**
   * Manually trigger a fatal overlay — useful for auth failures, etc.
   * @param {string} message
   */
  window.sfShowFatal = showFatalOverlay

  // ── Alpine.js component export ─────────────────────────────────────────────

  /**
   * Alpine.js data component — register with:
   *   Alpine.data('errorBoundary', window.errorBoundaryComponent)
   *
   * Exposes showToast() and showFatal() as Alpine reactive methods.
   */
  window.errorBoundaryComponent = function () {
    return {
      showToast: showToast,
      showFatal: showFatalOverlay,
    }
  }

}(window, document))
