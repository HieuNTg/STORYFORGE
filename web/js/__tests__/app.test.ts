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
  if (up.includes('MEDIA') || up.includes('IMAGE')) return 3
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
    // Piece O: continuation context — populated when the user clicks "Tiếp từ ch.N"
    // on the library card. Pipeline page reads this to render the resume callout.
    continuationMode: false as boolean,
    continuationMeta: null as {
      checkpoint: string
      title: string
      chapterCount: number
      genre: string
      resumeFromChapter?: number
      targetChapters?: number
      interruptedAt?: string
    } | null,
    // Piece P: timing for the post-resume success ribbon
    runStartedAt: null as number | null,
    runFinishedAt: null as number | null,
    // Piece Q: deep-link flag handed off from the ribbon CTA to library.openStory
    pendingJumpAfterOpen: false as boolean,
    form: {
      idea: '',
      title: '',
      num_chapters: 5,
    },

    _detectLayer(msg: string): number {
      return detectLayer(msg, this.progress)
    },

    validate(): string | null {
      const idea = (this.form.idea || '').trim()
      if (!idea || idea.length < 10) return 'Please enter a story idea (at least 10 characters).'
      return null
    },

    // Piece O: dismiss callout without nuking unrelated pipeline state.
    dismissContinuationCallout(): void {
      this.continuationMode = false
      this.continuationMeta = null
    },

    // Piece P: clear continuationMeta when the user dismisses or follows
    // the success ribbon's reader CTA.
    clearResumeRibbon(): void {
      this.continuationMeta = null
    },

    reset(): void {
      this.status = 'idle'
      this.logs = []
      this.livePreview = ''
      this.progress = 0
      this.result = null
      this.error = null
      this.checkpoints = []
      this.continuationMode = false
      this.continuationMeta = null
      this.runStartedAt = null
      this.runFinishedAt = null
      this.pendingJumpAfterOpen = false
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
  it('returns 3 for media/image keywords', () => {
    expect(detectLayer('Generating MEDIA files', 0)).toBe(3)
    expect(detectLayer('Processing IMAGE', 0)).toBe(3)
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

// ============================================================================
// Piece O: continuation callout dismiss
// ============================================================================
describe('pipelineStore.dismissContinuationCallout()', () => {
  it('clears continuationMode + continuationMeta but leaves status untouched', () => {
    const store = createPipelineStore()
    store.continuationMode = true
    store.continuationMeta = {
      checkpoint: 'tale.json',
      title: 'A Tale',
      chapterCount: 3,
      genre: 'Tiên Hiệp',
      resumeFromChapter: 4,
      targetChapters: 10,
      interruptedAt: '2026-05-03T20:00:00Z',
    }
    store.status = 'idle'

    store.dismissContinuationCallout()

    expect(store.continuationMode).toBe(false)
    expect(store.continuationMeta).toBeNull()
    // Status should not be reset — user may still want to keep their form.
    expect(store.status).toBe('idle')
  })

  it('reset() also clears continuation state', () => {
    const store = createPipelineStore()
    store.continuationMode = true
    store.continuationMeta = {
      checkpoint: 'x', title: 'y', chapterCount: 1, genre: 'z',
      resumeFromChapter: 2, targetChapters: 5,
    }

    store.reset()

    expect(store.continuationMode).toBe(false)
    expect(store.continuationMeta).toBeNull()
  })
})

// ============================================================================
// Piece P: post-resume success ribbon
// ============================================================================

// Mirrors the ribbon's x-if predicate in index.html so the ribbon shows only
// after a resume run finishes (continuationMeta survives until the user
// dismisses or follows the reader CTA).
function shouldShowResumeRibbon(store: {
  status: string
  continuationMeta: { resumeFromChapter?: number } | null
}): boolean {
  return store.status === 'done'
    && !!store.continuationMeta
    && !!store.continuationMeta.resumeFromChapter
}

// Mirrors pipeline.ts formatElapsedVi — short, ≤ minute granularity since
// resume deltas typically finish in seconds-to-minutes.
function formatElapsedVi(startedAt: number | null, finishedAt: number | null): string {
  if (startedAt == null || finishedAt == null || finishedAt < startedAt) return ''
  const diff = finishedAt - startedAt
  if (diff < 60_000) return `${Math.max(1, Math.floor(diff / 1000))} giây`
  const minutes = Math.floor(diff / 60_000)
  return `${minutes} phút`
}

describe('Piece P: post-resume success ribbon', () => {
  it('shows when status is done AND continuationMeta has resumeFromChapter', () => {
    const store = createPipelineStore()
    store.status = 'done'
    store.continuationMeta = {
      checkpoint: 'tale.json',
      title: 'A Tale',
      chapterCount: 4,
      genre: 'Tiên Hiệp',
      resumeFromChapter: 5,
      targetChapters: 10,
    }
    expect(shouldShowResumeRibbon(store)).toBe(true)
  })

  it('hides for non-resume runs (no resumeFromChapter)', () => {
    const store = createPipelineStore()
    store.status = 'done'
    store.continuationMeta = {
      checkpoint: 'tale.json',
      title: 'A Tale',
      chapterCount: 0,
      genre: 'Tiên Hiệp',
      // no resumeFromChapter — plain continuation, ribbon must stay hidden
    }
    expect(shouldShowResumeRibbon(store)).toBe(false)
  })

  it('hides while pipeline is still running', () => {
    const store = createPipelineStore()
    store.status = 'running'
    store.continuationMeta = {
      checkpoint: 'tale.json', title: 'A Tale', chapterCount: 4, genre: 'x',
      resumeFromChapter: 5, targetChapters: 10,
    }
    expect(shouldShowResumeRibbon(store)).toBe(false)
  })

  it('clearResumeRibbon() drops continuationMeta so the ribbon disappears', () => {
    const store = createPipelineStore()
    store.status = 'done'
    store.continuationMeta = {
      checkpoint: 'tale.json', title: 'A Tale', chapterCount: 4, genre: 'x',
      resumeFromChapter: 5, targetChapters: 10,
    }
    expect(shouldShowResumeRibbon(store)).toBe(true)

    store.clearResumeRibbon()

    expect(store.continuationMeta).toBeNull()
    // Status untouched — user still has their result panel open.
    expect(store.status).toBe('done')
    expect(shouldShowResumeRibbon(store)).toBe(false)
  })

  it('formatElapsedVi() returns "X giây" under a minute', () => {
    expect(formatElapsedVi(1000, 4500)).toBe('3 giây')
    // Sub-second still floors to 1 (don't show "0 giây").
    expect(formatElapsedVi(1000, 1500)).toBe('1 giây')
  })

  it('formatElapsedVi() returns "Y phút" once over a minute', () => {
    expect(formatElapsedVi(0, 3 * 60_000)).toBe('3 phút')
  })

  it('formatElapsedVi() returns empty string when timing is missing', () => {
    expect(formatElapsedVi(null, 1000)).toBe('')
    expect(formatElapsedVi(1000, null)).toBe('')
    // Negative diff (clock skew) is treated as missing.
    expect(formatElapsedVi(2000, 1000)).toBe('')
  })
})

// ============================================================================
// Piece Q: deep-link jump to first new chapter after resume
// ============================================================================

// Mirrors the openReaderFromRibbon → library.openStory handoff. The CTA sets
// pendingJumpAfterOpen on the pipeline store; library.openStory reads it once
// and triggers jumpToNewChapter(). Pure flag-handoff logic — DOM/SPA nav not
// in scope.
describe('Piece Q: pendingJumpAfterOpen handoff', () => {
  it('openReaderFromRibbon flips the flag so library.openStory can consume it', () => {
    const store = createPipelineStore()
    expect(store.pendingJumpAfterOpen).toBe(false)

    // Simulate the CTA: set flag, then clearResumeRibbon (must NOT clobber flag)
    store.pendingJumpAfterOpen = true
    store.continuationMeta = {
      checkpoint: 'tale.json', title: 'Tale', chapterCount: 4, genre: 'x',
      resumeFromChapter: 5, targetChapters: 10,
    }
    store.clearResumeRibbon()

    // Ribbon dismissed but the deep-link intent survives the navigation.
    expect(store.continuationMeta).toBeNull()
    expect(store.pendingJumpAfterOpen).toBe(true)
  })

  it('library.openStory consumes the flag exactly once', () => {
    const store = createPipelineStore()
    store.pendingJumpAfterOpen = true

    // Mirror library.openStory consumption:
    //   if (pipelineStore.pendingJumpAfterOpen) {
    //     pipelineStore.pendingJumpAfterOpen = false
    //     this.jumpToNewChapter()
    //   }
    let jumpedTimes = 0
    const consume = (): void => {
      if (store.pendingJumpAfterOpen) {
        store.pendingJumpAfterOpen = false
        jumpedTimes += 1
      }
    }

    consume()
    expect(jumpedTimes).toBe(1)
    expect(store.pendingJumpAfterOpen).toBe(false)

    // Second openStory call (e.g., user navigates back) must NOT re-jump.
    consume()
    expect(jumpedTimes).toBe(1)
  })

  it('reset() clears pendingJumpAfterOpen', () => {
    const store = createPipelineStore()
    store.pendingJumpAfterOpen = true
    store.reset()
    expect(store.pendingJumpAfterOpen).toBe(false)
  })
})
