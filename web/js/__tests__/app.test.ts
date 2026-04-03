/**
 * app.test.ts — Unit tests for StoryForge SPA logic (app.ts).
 *
 * app.ts registers Alpine stores via document's alpine:init event and accesses
 * window globals. We test the pure logic pieces in isolation:
 *   - resolveHash(): validates and strips URL hash prefixes
 *   - _detectLayer(): maps log messages to pipeline layer numbers
 *   - toggleDarkMode(): toggles .dark class on <html> and persists to localStorage
 *   - navigate(): updates page + hash
 *   - setLoading() / clearLoading(): loading overlay state
 *   - pipeline.run() validation: short idea returns error
 *   - pipeline.reset(): returns to idle state
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Extracted pure functions from app.ts (no Alpine dependency)
// ---------------------------------------------------------------------------

const NAV_IDS = ['pipeline', 'library', 'reader', 'export', 'analytics', 'branching', 'settings', 'guide']

function resolveHash(raw: string): string | null {
  const id = raw.replace(/^#?\/?/, '')
  return NAV_IDS.includes(id) ? id : null
}

function detectLayer(msg: string, currentProgress: number): number {
  const up = msg.toUpperCase()
  if (up.includes('MEDIA') || up.includes('IMAGE') || up.includes('AUDIO')) return 4
  if (up.includes('LAYER 3') || up.includes('STORYBOARD') || up.includes('VIDEO')) return 3
  if (up.includes('LAYER 2') || up.includes('MÔ PHỎNG') || up.includes('ENHANCE')) return 2
  if (up.includes('LAYER 1') || up.includes('TẠO TRUYỆN') || up.includes('CHƯƠNG')) return 1
  return currentProgress || 0
}

// ---------------------------------------------------------------------------
// App store logic extracted as a plain object (mirrors Alpine store methods)
// ---------------------------------------------------------------------------
function createAppStore() {
  const store = {
    page: 'pipeline' as string,
    sidebarOpen: true,
    isLoading: false,
    loadingMessage: '' as string,
    darkMode: false,

    toggleDarkMode(): void {
      this.darkMode = !this.darkMode
      if (this.darkMode) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
      document.documentElement.style.colorScheme = this.darkMode ? 'dark' : 'light'
      try { localStorage.setItem('sf_theme', this.darkMode ? 'dark' : 'light') } catch (_) {}
    },

    navigate(page: string): void {
      this.page = page
      if (window.innerWidth <= 768) this.sidebarOpen = false
      window.location.hash = page
    },

    setLoading(msg?: string): void {
      this.isLoading = true
      this.loadingMessage = msg || ''
    },

    clearLoading(): void {
      this.isLoading = false
      this.loadingMessage = ''
    },

    toggleSidebar(): void {
      this.sidebarOpen = !this.sidebarOpen
    },
  }
  return store
}

// ---------------------------------------------------------------------------
// Pipeline store logic (just the stateful parts we can test without Alpine SSE)
// ---------------------------------------------------------------------------
function createPipelineStore() {
  return {
    status: 'idle' as string,
    logs: [] as string[],
    livePreview: '' as string,
    progress: 0,
    result: null as unknown,
    error: null as string | null,
    checkpoints: [] as unknown[],
    form: {
      idea: '',
      title: '',
    },

    _detectLayer(msg: string): number {
      return detectLayer(msg, this.progress)
    },

    validate(): string | null {
      const idea = (this.form.idea || '').trim()
      if (!idea || idea.length < 10) return 'Please enter a story idea (at least 10 characters).'
      return null
    },

    reset(): void {
      this.status = 'idle'
      this.logs = []
      this.livePreview = ''
      this.progress = 0
      this.result = null
      this.error = null
      this.checkpoints = []
    },
  }
}

// ============================================================================
// resolveHash()
// ============================================================================
describe('resolveHash()', () => {
  it('returns page id for a plain hash like #pipeline', () => {
    expect(resolveHash('#pipeline')).toBe('pipeline')
  })

  it('strips #/ prefix (deep-link format)', () => {
    expect(resolveHash('#/library')).toBe('library')
  })

  it('accepts bare id without hash prefix', () => {
    expect(resolveHash('reader')).toBe('reader')
  })

  it('returns null for unknown page ids', () => {
    expect(resolveHash('#unknown-page')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(resolveHash('')).toBeNull()
  })

  it('resolves all known navigation ids', () => {
    for (const id of NAV_IDS) {
      expect(resolveHash(`#${id}`)).toBe(id)
    }
  })
})

// ============================================================================
// detectLayer()
// ============================================================================
describe('detectLayer()', () => {
  it('returns 4 for media/image/audio keywords', () => {
    expect(detectLayer('Generating MEDIA files', 0)).toBe(4)
    expect(detectLayer('Processing IMAGE', 0)).toBe(4)
    expect(detectLayer('AUDIO generation complete', 0)).toBe(4)
  })

  it('returns 3 for LAYER 3/storyboard/video keywords', () => {
    expect(detectLayer('LAYER 3: building storyboard', 0)).toBe(3)
    expect(detectLayer('Creating STORYBOARD', 0)).toBe(3)
    expect(detectLayer('VIDEO export started', 0)).toBe(3)
  })

  it('returns 2 for LAYER 2/enhance keywords', () => {
    expect(detectLayer('LAYER 2 running', 0)).toBe(2)
    expect(detectLayer('ENHANCE story quality', 0)).toBe(2)
  })

  it('returns 1 for LAYER 1/story creation keywords', () => {
    expect(detectLayer('LAYER 1: TẠO TRUYỆN', 0)).toBe(1)
    expect(detectLayer('Writing CHƯƠNG 1', 0)).toBe(1)
  })

  it('returns current progress for unrecognised messages', () => {
    expect(detectLayer('Initialising...', 2)).toBe(2)
    expect(detectLayer('Some random log', 0)).toBe(0)
  })
})

// ============================================================================
// App store — toggleDarkMode
// ============================================================================
describe('appStore.toggleDarkMode()', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark')
    localStorage.clear()
  })

  it('adds .dark to <html> when toggling from light mode', () => {
    const store = createAppStore()
    store.darkMode = false
    store.toggleDarkMode()
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(store.darkMode).toBe(true)
  })

  it('removes .dark from <html> when toggling back to light', () => {
    const store = createAppStore()
    store.darkMode = true
    document.documentElement.classList.add('dark')
    store.toggleDarkMode()
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(store.darkMode).toBe(false)
  })

  it('persists theme to localStorage', () => {
    const store = createAppStore()
    store.darkMode = false
    store.toggleDarkMode()
    expect(localStorage.getItem('sf_theme')).toBe('dark')
    store.toggleDarkMode()
    expect(localStorage.getItem('sf_theme')).toBe('light')
  })
})

// ============================================================================
// App store — setLoading / clearLoading
// ============================================================================
describe('appStore.setLoading() / clearLoading()', () => {
  it('setLoading sets isLoading to true with optional message', () => {
    const store = createAppStore()
    store.setLoading('Generating story...')
    expect(store.isLoading).toBe(true)
    expect(store.loadingMessage).toBe('Generating story...')
  })

  it('setLoading sets empty message when none provided', () => {
    const store = createAppStore()
    store.setLoading()
    expect(store.isLoading).toBe(true)
    expect(store.loadingMessage).toBe('')
  })

  it('clearLoading resets both flags', () => {
    const store = createAppStore()
    store.setLoading('Working...')
    store.clearLoading()
    expect(store.isLoading).toBe(false)
    expect(store.loadingMessage).toBe('')
  })
})

// ============================================================================
// App store — navigate
// ============================================================================
describe('appStore.navigate()', () => {
  it('updates the page property', () => {
    const store = createAppStore()
    store.navigate('library')
    expect(store.page).toBe('library')
  })

  it('updates window.location.hash', () => {
    const store = createAppStore()
    store.navigate('settings')
    expect(window.location.hash).toBe('#settings')
  })
})

// ============================================================================
// Pipeline store — validation
// ============================================================================
describe('pipelineStore validation', () => {
  it('returns error message for empty idea', () => {
    const store = createPipelineStore()
    store.form.idea = ''
    expect(store.validate()).toContain('at least 10 characters')
  })

  it('returns error for idea shorter than 10 characters', () => {
    const store = createPipelineStore()
    store.form.idea = 'short'
    expect(store.validate()).not.toBeNull()
  })

  it('returns null when idea meets minimum length', () => {
    const store = createPipelineStore()
    store.form.idea = 'A great story about dragons and magic'
    expect(store.validate()).toBeNull()
  })
})

// ============================================================================
// Pipeline store — reset
// ============================================================================
describe('pipelineStore.reset()', () => {
  it('returns all fields to their initial values', () => {
    const store = createPipelineStore()
    store.status = 'running'
    store.logs = ['log1', 'log2']
    store.progress = 3
    store.error = 'oops'

    store.reset()

    expect(store.status).toBe('idle')
    expect(store.logs).toEqual([])
    expect(store.progress).toBe(0)
    expect(store.error).toBeNull()
    expect(store.result).toBeNull()
    expect(store.checkpoints).toEqual([])
  })
})
