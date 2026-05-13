/**
 * globals.d.ts — Type declarations for browser globals used by StoryForge.
 *
 * Alpine.js is loaded from CDN, API client and StorageManager are loaded
 * as plain <script> tags. This file provides type information so tsc can
 * check the codebase without import/export module boundaries.
 */

/* ── Alpine.js ─────────────────────────────────────────────────────────── */

/**
 * Alpine magic properties injected at runtime into every component.
 * Extend this interface when page components need additional magic properties.
 */
interface AlpineComponent {
  $watch(expr: string | (() => unknown), cb: (val: unknown) => void): void;
  /** Called with a callback or awaited with no args (returns Promise). */
  $nextTick(): Promise<void>;
  $nextTick(cb: () => void): void;
  $refs: Record<string, HTMLElement>;
  $el: HTMLElement;
  $store: typeof Alpine.store;
  $dispatch(event: string, detail?: unknown): void;
}

interface AlpineStatic {
  /** Define or retrieve an Alpine store. ThisType<T> gives `this` proper typing inside methods. */
  store<T extends Record<string, any>>(name: string, value: T & ThisType<T>): void
  store(name: string): any
  /** Alpine.data accepts any object-returning factory — typed interface returned by factory, not Record<string, unknown> */
  data(name: string, fn: (...args: any[]) => object): void
  start(): void
}

declare var Alpine: AlpineStatic

/* ── API Client ────────────────────────────────────────────────────────── */

interface StreamEvent {
  /**
   * Two conventions exist in the backend (see m2-sse-payload-audit.md):
   *   - /pipeline/run, /pipeline/resume                 → 'session' | 'log' | 'stream' | 'done' | 'error'
   *   - /pipeline/continue, /collaborative-chapter,
   *     /polish, /check-consistency, /write-from-path  → 'session' | 'progress' | 'stream' | 'done' | 'error' (+ 'start' on path-write)
   * The frontend api-client synthesises 'interrupted' on transport failures.
   * 'chapter' is reserved for a future typed event and is NOT emitted today.
   */
  type:
    | 'session'
    | 'log'
    | 'progress'
    | 'start'
    | 'stream'
    | 'done'
    | 'error'
    | 'interrupted'
  /** `data` is string for most event types; the `done` event delivers a parsed PipelineResult object */
  data: unknown
  session_id?: string
  /** Server-side counter attached only to `log` events. */
  logs_count?: number
  payload?: unknown
}

interface ApiClient {
  base: string
  get<T = unknown>(path: string): Promise<T>
  post<T = unknown>(path: string, body?: Record<string, unknown> | unknown[]): Promise<T>
  put<T = unknown>(path: string, body?: Record<string, unknown> | unknown[]): Promise<T>
  patch<T = unknown>(path: string, body?: Record<string, unknown> | unknown[]): Promise<T>
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
  __sf_i18n: {
    locale: 'vi' | 'en'
    translations: Record<string, Record<string, string>>
    t(key: string): string
    setLocale(locale: 'vi' | 'en'): void
    loadTranslations(): Promise<void>
  }
  storageManager: StorageManagerInterface
  sfShowToast: (message: string, level?: 'error' | 'warning') => void
  sfShowFatal: (message: string) => void
  errorBoundaryComponent: () => { showToast: typeof window.sfShowToast; showFatal: typeof window.sfShowFatal }
}
