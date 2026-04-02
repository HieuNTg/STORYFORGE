/**
 * api-client.test.ts — Unit tests for the typed StoryForge API client.
 *
 * Covers:
 *   - GET / POST / PUT / DELETE fetch wrapper methods
 *   - Error handling when the server returns a non-OK status
 *   - SSE stream() generator: happy path, interrupted stream, error events
 *   - download() anchor-click helper
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createAPI } from './helpers/create-api'

// ---------------------------------------------------------------------------
// Fresh API instance per test
// ---------------------------------------------------------------------------
// eslint-disable-next-line @typescript-eslint/no-explicit-any
let API: any

beforeEach(() => {
  API = createAPI()
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

interface MockResponseOptions {
  ok?: boolean
  status?: number
  body?: unknown
  blob?: Blob | null
}

function mockResponse({ ok = true, status = 200, body = {}, blob = null }: MockResponseOptions = {}) {
  return {
    ok,
    status,
    json: vi.fn().mockResolvedValue(body),
    blob: vi.fn().mockResolvedValue(blob ?? new Blob()),
  }
}

interface TestStreamEvent {
  type: string
  data: string
  payload?: unknown
}

function sseStream(lines: string[]) {
  const encoder = new TextEncoder()
  const chunks = lines.map((l) => encoder.encode(l + '\n'))
  let index = 0
  return {
    getReader() {
      return {
        async read(): Promise<{ done: boolean; value: Uint8Array | undefined }> {
          if (index >= chunks.length) return { done: true, value: undefined }
          return { done: false, value: chunks[index++] }
        },
        releaseLock: vi.fn(),
      }
    },
  }
}

// ============================================================================
// GET
// ============================================================================
describe('API.get()', () => {
  it('calls fetch with the correct URL and returns parsed JSON', async () => {
    const payload = { story: 'test' }
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: payload }))

    const result = await API.get('/stories/1')

    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch).toHaveBeenCalledWith('/api/stories/1')
    expect(result).toEqual(payload)
  })

  it('throws a descriptive error when server returns 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 404 }))

    await expect(API.get('/stories/999')).rejects.toThrow('GET /stories/999: 404')
  })

  it('propagates network-level errors (fetch rejects)', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError('Network failure'))

    await expect(API.get('/stories')).rejects.toThrow('Network failure')
  })
})

// ============================================================================
// POST
// ============================================================================
describe('API.post()', () => {
  it('sends JSON body and Content-Type header', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { id: 42 } }))

    const result = await API.post('/stories', { title: 'My Story' })

    expect(fetch).toHaveBeenCalledWith('/api/stories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'My Story' }),
    })
    expect(result).toEqual({ id: 42 })
  })

  it('sends an empty object body when no body argument is provided', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse())

    await API.post('/stories')

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [, init] = (fetch as any).mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({})
  })

  it('throws when server returns 422 Unprocessable Entity', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 422 }))

    await expect(API.post('/stories', { title: '' })).rejects.toThrow('POST /stories: 422')
  })
})

// ============================================================================
// PUT
// ============================================================================
describe('API.put()', () => {
  it('calls fetch with PUT method and serialised body', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { updated: true } }))

    const result = await API.put('/stories/1', { title: 'Updated' })

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const [url, init] = (fetch as any).mock.calls[0]
    expect(url).toBe('/api/stories/1')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body)).toEqual({ title: 'Updated' })
    expect(result).toEqual({ updated: true })
  })

  it('throws on non-OK response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 403 }))

    await expect(API.put('/stories/1', {})).rejects.toThrow('PUT /stories/1: 403')
  })
})

// ============================================================================
// DELETE
// ============================================================================
describe('API.del()', () => {
  it('calls fetch with DELETE method', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ body: { deleted: true } }))

    const result = await API.del('/stories/1')

    expect(fetch).toHaveBeenCalledWith('/api/stories/1', { method: 'DELETE' })
    expect(result).toEqual({ deleted: true })
  })

  it('throws on non-OK response', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 404 }))

    await expect(API.del('/stories/999')).rejects.toThrow('DELETE /stories/999: 404')
  })
})

// ============================================================================
// SSE stream()
// ============================================================================
describe('API.stream()', () => {
  it('yields parsed SSE events from the response body', async () => {
    const events = [
      'data: {"type":"progress","data":"chunk 1"}',
      'data: {"type":"done","data":"finished"}',
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: sseStream(events),
    })

    const received: TestStreamEvent[] = []
    for await (const event of API.stream('/generate', { prompt: 'hi' })) {
      received.push(event)
    }

    expect(received).toHaveLength(2)
    expect(received[0]).toEqual({ type: 'progress', data: 'chunk 1' })
    expect(received[1]).toEqual({ type: 'done', data: 'finished' })
  })

  it('yields an interrupted event when stream ends without a done event', async () => {
    const events = ['data: {"type":"progress","data":"partial"}']
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: sseStream(events),
    })

    const received: TestStreamEvent[] = []
    for await (const event of API.stream('/generate', {})) {
      received.push(event)
    }

    const last = received[received.length - 1]
    expect(last.type).toBe('interrupted')
  })

  it('yields an interrupted event when the reader throws mid-stream', async () => {
    let callCount = 0
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: {
        getReader() {
          return {
            async read() {
              callCount++
              if (callCount === 1) {
                return { done: false, value: new TextEncoder().encode('data: {"type":"progress"}\n') }
              }
              throw new Error('Connection reset')
            },
            releaseLock: vi.fn(),
          }
        },
      },
    })

    const received: TestStreamEvent[] = []
    for await (const event of API.stream('/generate', {})) {
      received.push(event)
    }

    const interrupted = received.find((e) => e.type === 'interrupted')
    expect(interrupted).toBeDefined()
    expect(interrupted!.data).toContain('Connection reset')
  })

  it('throws immediately when SSE endpoint returns a non-OK status', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 503 }))

    const gen = API.stream('/generate', {})
    await expect(gen.next()).rejects.toThrow('SSE /generate: 503')
  })

  it('silently skips non-data lines (comment/empty lines)', async () => {
    const events = [
      ': keep-alive',
      '',
      'data: {"type":"done","data":"ok"}',
    ]
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: sseStream(events),
    })

    const received: TestStreamEvent[] = []
    for await (const event of API.stream('/generate', {})) {
      received.push(event)
    }

    expect(received.every((e) => e.type !== undefined)).toBe(true)
    expect(received.find((e) => e.type === 'done')).toBeDefined()
  })
})

// ============================================================================
// download()
// ============================================================================
describe('API.download()', () => {
  it('creates an anchor element, clicks it, and revokes the object URL', async () => {
    const fakeBlob = new Blob(['pdf-content'], { type: 'application/pdf' })
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: vi.fn().mockResolvedValue(fakeBlob),
    })

    const fakeObjectURL = 'blob:http://localhost/fake-123'
    globalThis.URL.createObjectURL = vi.fn().mockReturnValue(fakeObjectURL)
    globalThis.URL.revokeObjectURL = vi.fn()

    const clickSpy = vi.fn()
    const fakeAnchor = { href: '', download: '', click: clickSpy }
    vi.spyOn(document, 'createElement').mockReturnValue(fakeAnchor as unknown as HTMLElement)

    await API.download('/export/pdf', 'story.pdf')

    expect(URL.createObjectURL).toHaveBeenCalledWith(fakeBlob)
    expect(fakeAnchor.download).toBe('story.pdf')
    expect(clickSpy).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(fakeObjectURL)
  })

  it('throws when the download endpoint returns a non-OK status', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(mockResponse({ ok: false, status: 500 }))

    await expect(API.download('/export/pdf', 'story.pdf')).rejects.toThrow('Download /export/pdf: 500')
  })
})
