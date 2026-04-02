/**
 * globals.d.ts — Type declarations for browser globals used by StoryForge.
 *
 * Alpine.js is loaded from CDN, API client and StorageManager are loaded
 * as plain <script> tags. This file provides type information so tsc can
 * check the codebase without import/export module boundaries.
 */

/* ── Alpine.js ─────────────────────────────────────────────────────────── */

interface AlpineStatic {
  /** Define or retrieve an Alpine store. ThisType<T> gives `this` proper typing inside methods. */
  store<T extends Record<string, any>>(name: string, value: T & ThisType<T>): void
  store(name: string): any
  data(name: string, fn: (...args: any[]) => Record<string, unknown>): void
  start(): void
}

declare var Alpine: AlpineStatic

/* ── API Client ────────────────────────────────────────────────────────── */

interface StreamEvent {
  type: 'progress' | 'chapter' | 'done' | 'error' | 'interrupted' | 'session' | 'log' | 'stream'
  data: string
  session_id?: string
  payload?: unknown
}

interface ApiClient {
  base: string
  get<T = unknown>(path: string): Promise<T>
  post<T = unknown>(path: string, body?: Record<string, unknown> | unknown[]): Promise<T>
  put<T = unknown>(path: string, body?: Record<string, unknown> | unknown[]): Promise<T>
  del<T = unknown>(path: string): Promise<T>
  stream(path: string, body: Record<string, unknown> | unknown[]): AsyncGenerator<StreamEvent>
  streamBuffered(path: string, body: Record<string, unknown> | unknown[], bufferMs?: number): AsyncGenerator<StreamEvent>
  download(path: string, filename: string): Promise<void>
}

// Use `var` so the implementation in api-client.ts can redeclare it
declare var API: ApiClient

/* ── Storage Manager ───────────────────────────────────────────────────── */

interface StorageManagerInterface {
  init(): Promise<void>
  setItem(key: string, value: string): Promise<void>
  getItem(key: string): Promise<string | null>
  removeItem(key: string): Promise<void>
  clear(): Promise<void>
  isUsingFallback(): boolean
}

/* ── Window augmentation ───────────────────────────────────────────────── */

interface Window {
  storageManager: StorageManagerInterface
  sfShowToast: (message: string, level?: 'error' | 'warning') => void
  sfShowFatal: (message: string) => void
  errorBoundaryComponent: () => { showToast: typeof window.sfShowToast; showFatal: typeof window.sfShowFatal }
}
