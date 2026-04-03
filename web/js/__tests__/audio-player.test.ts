/**
 * audio-player.test.ts — Unit tests for the audioPlayer Alpine.js component.
 *
 * audioPlayer() returns a plain object with state + methods; we test
 * those directly without needing Alpine's reactivity system.
 *
 * Covers:
 *   - progressPercent computed property
 *   - timeDisplay computed property
 *   - setRate() updates playbackRate and applies to Audio element
 *   - pause() delegates to the internal Audio element
 *   - generateAudio() fetches and caches audio URL; returns null on error
 *   - seek() calculates correct currentTime from mouse position
 *   - destroy() nullifies _audio reference
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Inline audioPlayer logic (mirrors source — avoids Alpine/Alpine.store dep)
// ---------------------------------------------------------------------------

interface ChapterData {
  content: string
  title?: string
  [key: string]: unknown
}

interface AudioGenerateResponse {
  audio_url: string
  error?: string
}

interface AudioStatusResponse {
  exists: boolean
  audio_url: string
}

function createAudioPlayer(chaptersOverride?: ChapterData[]) {
  const player = {
    visible: false as boolean,
    playing: false as boolean,
    loading: false as boolean,
    error: '' as string,
    currentChapter: 0 as number,
    progress: 0 as number,
    duration: 0 as number,
    playbackRate: 1 as number,
    audioCache: {} as Record<number, string>,
    _audio: null as HTMLAudioElement | null,

    get chapters(): ChapterData[] {
      return chaptersOverride ?? []
    },

    get currentChapterData(): ChapterData | null {
      return this.chapters[this.currentChapter] || null
    },

    get progressPercent(): number {
      if (!this.duration) return 0
      return Math.round((this.progress / this.duration) * 100)
    },

    get timeDisplay(): string {
      const fmt = (s: number) => {
        const m = Math.floor(s / 60)
        return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`
      }
      return `${fmt(this.progress)} / ${fmt(this.duration)}`
    },

    _initAudio(): void {
      if (this._audio) return
      // In jsdom, Audio is not defined by default — we mock it below in tests
      this._audio = new (globalThis as unknown as { Audio: new () => HTMLAudioElement }).Audio()
      this._audio.onended = () => this._onEnded()
      this._audio.ontimeupdate = () => {
        this.progress = this._audio!.currentTime
        this.duration = this._audio!.duration || 0
      }
      this._audio.onplay = () => { this.playing = true }
      this._audio.onpause = () => { this.playing = false }
      this._audio.onerror = () => {
        this.error = 'Audio playback error'
        this.playing = false
        this.loading = false
      }
    },

    async generateAudio(chapterIndex: number): Promise<string | null> {
      const ch = this.chapters[chapterIndex]
      if (!ch) return null
      if (this.audioCache[chapterIndex]) return this.audioCache[chapterIndex]

      this.loading = true
      this.error = ''
      try {
        const res = await fetch(`/api/audio/generate/${chapterIndex}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: ch.content }),
        })
        const data: AudioGenerateResponse = await res.json()
        if (!res.ok || data.error) throw new Error(data.error || 'Generation failed')
        this.audioCache[chapterIndex] = data.audio_url
        return data.audio_url
      } catch (e) {
        this.error = (e as Error).message
        return null
      } finally {
        this.loading = false
      }
    },

    pause(): void {
      this._audio?.pause()
    },

    seek(e: { clientX: number; currentTarget: { getBoundingClientRect: () => { left: number; width: number } } }): void {
      if (!this._audio || !this.duration) return
      const rect = e.currentTarget.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      this._audio.currentTime = ratio * this.duration
    },

    setRate(rate: number | string): void {
      this.playbackRate = parseFloat(rate as string)
      if (this._audio) this._audio.playbackRate = this.playbackRate
    },

    _onEnded(): void {
      this.playing = false
      const next = this.currentChapter + 1
      if (next < this.chapters.length) {
        void this.play(next)
      }
    },

    async play(chapterIndex?: number): Promise<void> {
      const idx = chapterIndex ?? this.currentChapter
      this._initAudio()

      let url: string | undefined = this.audioCache[idx]
      if (!url) {
        try {
          const res = await fetch(`/api/audio/status/${idx}`)
          const data: AudioStatusResponse = await res.json()
          if (data.exists) url = data.audio_url
        } catch (_) {}
      }
      if (!url) url = await this.generateAudio(idx) ?? undefined
      if (!url) return

      this.currentChapter = idx
      this._audio!.src = url
      this._audio!.playbackRate = this.playbackRate
      await this._audio!.play()
    },

    destroy(): void {
      if (this._audio) { this._audio.pause(); this._audio = null }
    },
  }
  return player
}

// ---------------------------------------------------------------------------
// Minimal Audio mock
// ---------------------------------------------------------------------------
function makeAudioMock() {
  const mock = {
    src: '',
    currentTime: 0,
    duration: 0,
    playbackRate: 1,
    onended: null as (() => void) | null,
    ontimeupdate: null as (() => void) | null,
    onplay: null as (() => void) | null,
    onpause: null as (() => void) | null,
    onerror: null as (() => void) | null,
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
  }
  return mock
}

// ============================================================================
// Computed properties
// ============================================================================
describe('audioPlayer computed properties', () => {
  it('progressPercent returns 0 when duration is 0', () => {
    const p = createAudioPlayer()
    p.progress = 30
    p.duration = 0
    expect(p.progressPercent).toBe(0)
  })

  it('progressPercent calculates correctly', () => {
    const p = createAudioPlayer()
    p.progress = 45
    p.duration = 90
    expect(p.progressPercent).toBe(50)
  })

  it('timeDisplay formats mm:ss / mm:ss', () => {
    const p = createAudioPlayer()
    p.progress = 65   // 1:05
    p.duration = 190  // 3:10
    expect(p.timeDisplay).toBe('1:05 / 3:10')
  })

  it('timeDisplay pads single-digit seconds', () => {
    const p = createAudioPlayer()
    p.progress = 5
    p.duration = 9
    expect(p.timeDisplay).toBe('0:05 / 0:09')
  })
})

// ============================================================================
// setRate()
// ============================================================================
describe('audioPlayer.setRate()', () => {
  it('updates playbackRate from a number', () => {
    const p = createAudioPlayer()
    p.setRate(1.5)
    expect(p.playbackRate).toBe(1.5)
  })

  it('updates playbackRate from a string (select element value)', () => {
    const p = createAudioPlayer()
    p.setRate('2')
    expect(p.playbackRate).toBe(2)
  })

  it('propagates playbackRate to _audio when present', () => {
    const p = createAudioPlayer()
    const audio = makeAudioMock()
    p._audio = audio as unknown as HTMLAudioElement
    p.setRate(0.75)
    expect(audio.playbackRate).toBe(0.75)
  })
})

// ============================================================================
// pause()
// ============================================================================
describe('audioPlayer.pause()', () => {
  it('calls _audio.pause() when audio is initialised', () => {
    const p = createAudioPlayer()
    const audio = makeAudioMock()
    p._audio = audio as unknown as HTMLAudioElement
    p.pause()
    expect(audio.pause).toHaveBeenCalledOnce()
  })

  it('does not throw when _audio is null', () => {
    const p = createAudioPlayer()
    expect(() => p.pause()).not.toThrow()
  })
})

// ============================================================================
// generateAudio()
// ============================================================================
describe('audioPlayer.generateAudio()', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('fetches and caches audio URL on success', async () => {
    const chapters: ChapterData[] = [{ content: 'Once upon a time' }]
    const p = createAudioPlayer(chapters)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ audio_url: '/audio/ch0.mp3' }),
    })

    const url = await p.generateAudio(0)

    expect(url).toBe('/audio/ch0.mp3')
    expect(p.audioCache[0]).toBe('/audio/ch0.mp3')
    expect(p.loading).toBe(false)
    expect(p.error).toBe('')
  })

  it('returns cached URL without fetching again', async () => {
    const chapters: ChapterData[] = [{ content: 'Chapter content' }]
    const p = createAudioPlayer(chapters)
    p.audioCache[0] = '/audio/cached.mp3'

    globalThis.fetch = vi.fn()

    const url = await p.generateAudio(0)
    expect(url).toBe('/audio/cached.mp3')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('sets error and returns null on fetch failure', async () => {
    const chapters: ChapterData[] = [{ content: 'Chapter' }]
    const p = createAudioPlayer(chapters)

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: vi.fn().mockResolvedValue({ error: 'TTS service unavailable' }),
    })

    const url = await p.generateAudio(0)

    expect(url).toBeNull()
    expect(p.error).toBe('TTS service unavailable')
    expect(p.loading).toBe(false)
  })

  it('returns null for out-of-range chapter index', async () => {
    const p = createAudioPlayer([])
    const url = await p.generateAudio(5)
    expect(url).toBeNull()
  })
})

// ============================================================================
// seek()
// ============================================================================
describe('audioPlayer.seek()', () => {
  it('sets currentTime proportionally to click position', () => {
    const p = createAudioPlayer()
    const audio = makeAudioMock()
    p._audio = audio as unknown as HTMLAudioElement
    p.duration = 100

    const fakeEvent = {
      clientX: 150,
      currentTarget: {
        getBoundingClientRect: () => ({ left: 100, width: 100 }),
      },
    }

    p.seek(fakeEvent)
    // ratio = (150 - 100) / 100 = 0.5 → currentTime = 50
    expect(audio.currentTime).toBe(50)
  })

  it('clamps ratio to 0 for clicks before the bar', () => {
    const p = createAudioPlayer()
    const audio = makeAudioMock()
    p._audio = audio as unknown as HTMLAudioElement
    p.duration = 60

    p.seek({ clientX: 50, currentTarget: { getBoundingClientRect: () => ({ left: 100, width: 200 }) } })
    expect(audio.currentTime).toBe(0)
  })

  it('does nothing when _audio is null', () => {
    const p = createAudioPlayer()
    p.duration = 100
    expect(() =>
      p.seek({ clientX: 150, currentTarget: { getBoundingClientRect: () => ({ left: 100, width: 100 }) } })
    ).not.toThrow()
  })
})

// ============================================================================
// destroy()
// ============================================================================
describe('audioPlayer.destroy()', () => {
  it('pauses and nullifies _audio', () => {
    const p = createAudioPlayer()
    const audio = makeAudioMock()
    p._audio = audio as unknown as HTMLAudioElement

    p.destroy()

    expect(audio.pause).toHaveBeenCalledOnce()
    expect(p._audio).toBeNull()
  })
})
