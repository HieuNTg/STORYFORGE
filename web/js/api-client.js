/**
 * API Client — fetch wrapper for StoryForge API.
 * All methods return JSON or throw on error.
 */
const API = {
  base: '/api',

  async get(path) {
    const res = await fetch(this.base + path);
    if (!res.ok) throw new Error(`GET ${path}: ${res.status}`);
    return res.json();
  },

  async post(path, body = {}) {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`POST ${path}: ${res.status}`);
    return res.json();
  },

  async put(path, body = {}) {
    const res = await fetch(this.base + path, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PUT ${path}: ${res.status}`);
    return res.json();
  },

  async del(path) {
    const res = await fetch(this.base + path, { method: 'DELETE' });
    if (!res.ok) throw new Error(`DELETE ${path}: ${res.status}`);
    return res.json();
  },

  /**
   * SSE stream with interruption detection.
   * Yields events. If stream drops without 'done' event, yields { type: 'interrupted' }.
   */
  async *stream(path, body) {
    const res = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`SSE ${path}: ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let receivedDone = false;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events from buffer
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'done' || event.type === 'error') receivedDone = true;
              yield event;
            } catch (e) {
              console.warn('SSE parse error:', line);
            }
          }
        }
      }
    } catch (e) {
      // Connection lost mid-stream
      yield { type: 'interrupted', data: 'Connection lost: ' + e.message };
      return;
    }

    // Flush decoder for any remaining multi-byte chars
    buffer += decoder.decode();
    if (buffer.trim().startsWith('data: ')) {
      try {
        const event = JSON.parse(buffer.trim().slice(6));
        if (event.type === 'done' || event.type === 'error') receivedDone = true;
        yield event;
      } catch (e) { /* ignore partial */ }
    }

    // Stream ended without a done/error event — likely server crash
    if (!receivedDone) {
      yield { type: 'interrupted', data: 'Stream ended unexpectedly' };
    }
  },

  /**
   * Buffered SSE stream — batches events every 500ms to reduce re-renders.
   * Done/error/interrupted events flush buffer then yield immediately.
   */
  async *streamBuffered(path, body, bufferMs = 500) {
    let buffer = [];
    let lastFlush = Date.now();

    for await (const event of this.stream(path, body)) {
      const isFinal = ['done', 'error', 'interrupted'].includes(event.type);

      if (isFinal) {
        // Yield any buffered events first, then the final event
        for (const e of buffer) yield e;
        buffer = [];
        yield event;
        return;
      }

      buffer.push(event);

      // Flush buffer every bufferMs
      if (Date.now() - lastFlush >= bufferMs) {
        for (const e of buffer) yield e;
        buffer = [];
        lastFlush = Date.now();
      }
    }

    // Flush remaining events after loop ends
    for (const e of buffer) yield e;
  },

  /** Download a file from export endpoint */
  async download(path, filename) {
    const res = await fetch(this.base + path, { method: 'POST' });
    if (!res.ok) throw new Error(`Download ${path}: ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};
