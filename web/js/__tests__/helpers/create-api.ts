/**
 * Test helper — creates a fresh API client object for each test.
 * Mirrors the exact implementation from api-client.ts without eval/regex hacks.
 */

interface TestStreamEvent {
  type: string
  data: string
  session_id?: string
  payload?: unknown
}

type RequestBody = Record<string, unknown> | unknown[]

export function createAPI() {
  return {
    base: '/api',

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

    async *stream(path: string, body: RequestBody): AsyncGenerator<TestStreamEvent> {
      const res = await fetch(this.base + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(`SSE ${path}: ${res.status}`)

      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let receivedDone = false

      try {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event = JSON.parse(line.slice(6)) as TestStreamEvent
                if (event.type === 'done' || event.type === 'error') receivedDone = true
                yield event
              } catch {
                console.warn('SSE parse error:', line)
              }
            }
          }
        }
      } catch (e) {
        const message = e instanceof Error ? e.message : String(e)
        yield { type: 'interrupted', data: 'Connection lost: ' + message }
        return
      }

      buffer += decoder.decode()
      if (buffer.trim().startsWith('data: ')) {
        try {
          const event = JSON.parse(buffer.trim().slice(6)) as TestStreamEvent
          if (event.type === 'done' || event.type === 'error') receivedDone = true
          yield event
        } catch { /* ignore partial */ }
      }

      if (!receivedDone) {
        yield { type: 'interrupted', data: 'Stream ended unexpectedly' }
      }
    },

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
}
