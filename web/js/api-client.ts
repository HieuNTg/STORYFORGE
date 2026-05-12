/**
 * api-client.ts — Typed fetch wrapper for the StoryForge API.
 * All methods return JSON or throw on error.
 *
 * Loaded as a plain <script> tag — no ES module imports/exports.
 * Interfaces are declared globally in globals.d.ts.
 */

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

type RequestBody = Record<string, unknown> | unknown[]

/** Read a cookie value by name. Used for CSRF double-submit pattern. */
function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'))
  return match ? decodeURIComponent(match[1]) : null
}

/** Build headers for state-changing requests (POST/PUT/DELETE). */
function mutationHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const csrf = getCookie('csrf_token')
  if (csrf) headers['X-CSRF-Token'] = csrf
  return headers
}

/** Default timeout for regular requests (30 s). */
const DEFAULT_TIMEOUT_MS = 30_000
/** Extended timeout for SSE/streaming requests (5 min). */
const STREAM_TIMEOUT_MS = 300_000
/** Max retries for GET network errors (not HTTP errors). */
const GET_MAX_RETRIES = 2

/**
 * Wraps a fetch call with an AbortController timeout.
 * Returns the Response; cleans up the timer in all cases.
 */
async function fetchWithTimeout(
  url: string,
  opts: RequestInit,
  timeoutMs: number,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...opts, signal: controller.signal })
  } finally {
    clearTimeout(timeoutId)
  }
}

// ---------------------------------------------------------------------------
// API client object — available as window.API
// ---------------------------------------------------------------------------

var API: ApiClient = {
  base: '/api' as string,

  async get<T = unknown>(path: string): Promise<T> {
    let lastError: unknown
    for (let attempt = 0; attempt <= GET_MAX_RETRIES; attempt++) {
      try {
        const res = await fetchWithTimeout(this.base + path, {}, DEFAULT_TIMEOUT_MS)
        if (!res.ok) {
          let detail = `GET ${path}: ${res.status}`
          try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
          throw new Error(detail)
        }
        return res.json() as Promise<T>
      } catch (err) {
        // Don't retry HTTP errors (res.ok was false) — only network/timeout errors.
        if (err instanceof Error && err.message.startsWith('GET ')) throw err
        lastError = err
        if (attempt === GET_MAX_RETRIES) break
        // brief back-off between retries
        await new Promise<void>((resolve) => setTimeout(resolve, 200 * (attempt + 1)))
      }
    }
    throw lastError
  },

  async post<T = unknown>(path: string, body: RequestBody = {}): Promise<T> {
    const res = await fetchWithTimeout(
      this.base + path,
      {
        method: 'POST',
        headers: mutationHeaders(),
        body: JSON.stringify(body),
      },
      DEFAULT_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `POST ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }
    return res.json() as Promise<T>
  },

  async put<T = unknown>(path: string, body: RequestBody = {}): Promise<T> {
    const res = await fetchWithTimeout(
      this.base + path,
      {
        method: 'PUT',
        headers: mutationHeaders(),
        body: JSON.stringify(body),
      },
      DEFAULT_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `PUT ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }
    return res.json() as Promise<T>
  },

  async patch<T = unknown>(path: string, body?: RequestBody): Promise<T> {
    const res = await fetchWithTimeout(
      this.base + path,
      {
        method: 'PATCH',
        headers: mutationHeaders(),
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      },
      DEFAULT_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `PATCH ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }
    return res.json() as Promise<T>
  },

  async del<T = unknown>(path: string): Promise<T> {
    const res = await fetchWithTimeout(
      this.base + path,
      { method: 'DELETE', headers: mutationHeaders() },
      DEFAULT_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `DELETE ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }
    return res.json() as Promise<T>
  },

  /**
   * SSE stream with interruption detection.
   * Yields StreamEvent objects. If stream drops without a 'done' event,
   * yields `{ type: 'interrupted' }` so callers can handle gracefully.
   */
  async *stream(path: string, body: RequestBody): AsyncGenerator<StreamEvent> {
    const res = await fetchWithTimeout(
      this.base + path,
      {
        method: 'POST',
        headers: mutationHeaders(),
        body: JSON.stringify(body),
      },
      STREAM_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `SSE ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }

    // ReadableStream is guaranteed non-null for successful fetch responses
    const reader = res.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let receivedDone = false

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // Parse SSE events from buffer
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6)) as StreamEvent
              if (event.type === 'done' || event.type === 'error') receivedDone = true
              yield event
            } catch {
              console.warn('[SSE] JSON parse failed:', line)
            }
          }
        }
      }
    } catch (e) {
      // Connection lost mid-stream
      const message = e instanceof Error ? e.message : String(e)
      yield { type: 'interrupted', data: 'Connection lost: ' + message }
      return
    }

    // Flush decoder for any remaining multi-byte chars
    buffer += decoder.decode()
    if (buffer.trim().startsWith('data: ')) {
      try {
        const event = JSON.parse(buffer.trim().slice(6)) as StreamEvent
        if (event.type === 'done' || event.type === 'error') receivedDone = true
        yield event
      } catch {
        console.warn('[SSE] JSON parse failed (flush):', buffer.trim())
      }
    }

    // Stream ended without a done/error event — likely server crash
    if (!receivedDone) {
      yield { type: 'interrupted', data: 'Stream ended unexpectedly' }
    }
  },

  /**
   * Buffered SSE stream — batches events every `bufferMs` ms to reduce re-renders.
   * Done / error / interrupted events flush the buffer then yield immediately.
   */
  async *streamBuffered(
    path: string,
    body: RequestBody,
    bufferMs = 500,
  ): AsyncGenerator<StreamEvent> {
    let buffer: StreamEvent[] = []
    let lastFlush = Date.now()

    for await (const event of this.stream(path, body)) {
      const isFinal = (['done', 'error', 'interrupted'] as StreamEvent['type'][]).includes(event.type)

      if (isFinal) {
        // Yield any buffered events first, then the final event
        for (const e of buffer) yield e
        buffer = []
        yield event
        return
      }

      buffer.push(event)

      // Flush buffer every bufferMs
      if (Date.now() - lastFlush >= bufferMs) {
        for (const e of buffer) yield e
        buffer = []
        lastFlush = Date.now()
      }
    }

    // Flush remaining events after loop ends
    for (const e of buffer) yield e
  },

  /** Download a file from an export endpoint via anchor-click trick. */
  async download(path: string, filename: string): Promise<void> {
    const res = await fetchWithTimeout(
      this.base + path,
      { method: 'POST', headers: mutationHeaders() },
      DEFAULT_TIMEOUT_MS,
    )
    if (!res.ok) {
      let detail = `Download ${path}: ${res.status}`
      try { const body = await res.json(); if (body.detail) detail = body.detail } catch {}
      throw new Error(detail)
    }
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
