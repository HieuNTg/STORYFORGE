/**
 * api-client.ts — Typed fetch wrapper for the StoryForge API.
 * All methods return JSON or throw on error.
 *
 * Migrated from api-client.js — types added, logic unchanged.
 */

// ---------------------------------------------------------------------------
// Public interfaces — import these in other modules for type safety
// ---------------------------------------------------------------------------

/** Generic envelope for all JSON API responses. */
export interface ApiResponse<T = unknown> {
  data: T
  message?: string
}

/** Shape of an API error payload returned by FastAPI. */
export interface ApiError {
  detail: string
  status?: number
}

/** A single Server-Sent Event parsed from the SSE stream. */
export interface StreamEvent {
  type: 'progress' | 'chapter' | 'done' | 'error' | 'interrupted'
  data: string
  /** Optional structured payload (e.g. chapter JSON). */
  payload?: unknown
}

/** Story generation request payload sent to /generate endpoints. */
export interface StoryConfig {
  genre: string
  language: string
  targetWordCount: number
  chapterCount: number
  outline?: string
  temperature?: number
  model?: string
}

/** Full story data returned by the REST API. */
export interface StoryData {
  id: string
  title: string
  genre: string
  language: string
  synopsis: string
  wordCount: number
  status: string
  createdAt: string
  updatedAt: string
  chapters?: ChapterData[]
}

/** Individual chapter data. */
export interface ChapterData {
  id: string
  storyId: string
  index: number
  title: string
  content: string
  wordCount: number
}

/** Token usage statistics included in some API responses. */
export interface TokenUsage {
  promptTokens: number
  completionTokens: number
  totalTokens: number
  estimatedCostUsd?: number
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

type RequestBody = Record<string, unknown> | unknown[]

// ---------------------------------------------------------------------------
// API client object
// ---------------------------------------------------------------------------

const API = {
  base: '/api' as string,

  async get<T = unknown>(path: string): Promise<T> {
    const res = await fetch(this.base + path)
    if (!res.ok) throw new Error(`GET ${path}: ${res.status}`)
    return res.json() as Promise<T>
  },

  async post<T = unknown>(path: string, body: RequestBody = {}): Promise<T> {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`POST ${path}: ${res.status}`)
    return res.json() as Promise<T>
  },

  async put<T = unknown>(path: string, body: RequestBody = {}): Promise<T> {
    const res = await fetch(this.base + path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`PUT ${path}: ${res.status}`)
    return res.json() as Promise<T>
  },

  async del<T = unknown>(path: string): Promise<T> {
    const res = await fetch(this.base + path, { method: 'DELETE' })
    if (!res.ok) throw new Error(`DELETE ${path}: ${res.status}`)
    return res.json() as Promise<T>
  },

  /**
   * SSE stream with interruption detection.
   * Yields StreamEvent objects. If stream drops without a 'done' event,
   * yields `{ type: 'interrupted' }` so callers can handle gracefully.
   */
  async *stream(path: string, body: RequestBody): AsyncGenerator<StreamEvent> {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(`SSE ${path}: ${res.status}`)

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
              console.warn('SSE parse error:', line)
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
      } catch { /* ignore partial */ }
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
    const res = await fetch(this.base + path, { method: 'POST' })
    if (!res.ok) throw new Error(`Download ${path}: ${res.status}`)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}

export default API
