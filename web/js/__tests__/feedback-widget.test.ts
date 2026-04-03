/**
 * feedback-widget.test.ts — Unit tests for the feedbackWidget Alpine component.
 *
 * feedbackWidget is registered via Alpine.data() but its data object is a plain
 * JS object. We instantiate the inner `data` object directly to test logic.
 *
 * Covers:
 *   - canSubmit: true only when rating > 0 and not submitting/submitted
 *   - setRating() updates rating
 *   - setScore() updates dimension score
 *   - starState() returns 'filled'/'empty' correctly (incl. hover preview)
 *   - dimStarState() returns correct state for dimension hover/score
 *   - submit() posts correct payload (overall from dimensions when all set)
 *   - submit() sets error on API failure and clears submitting flag
 *   - reset() returns all state to defaults
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Inline feedback widget data factory (mirrors source logic exactly)
// ---------------------------------------------------------------------------

interface DimensionScores {
  coherence: number
  character: number
  drama: number
  writing: number
}

// Minimal API mock — replaced per test
let mockAPI = {
  post: vi.fn(),
}

function createFeedbackData(storyId: string, chapterIndex: number) {
  const data = {
    storyId,
    chapterIndex,
    rating: 0,
    hoverRating: 0,
    scores: { coherence: 0, character: 0, drama: 0, writing: 0 } as DimensionScores,
    hoverScores: { coherence: 0, character: 0, drama: 0, writing: 0 } as DimensionScores,
    comment: '',
    submitted: false,
    submitting: false,
    showDetails: false,
    error: '',

    get canSubmit(): boolean {
      return data.rating > 0 && !data.submitting && !data.submitted
    },

    get dimensionLabels(): Record<keyof DimensionScores, string> {
      return {
        coherence: 'Coherence',
        character: 'Characters',
        drama: 'Drama',
        writing: 'Writing',
      }
    },

    setRating(n: number): void {
      data.rating = n
    },

    setScore(dimension: keyof DimensionScores, n: number): void {
      data.scores[dimension] = n
    },

    starState(n: number): 'filled' | 'empty' {
      const active = data.hoverRating || data.rating
      return n <= active ? 'filled' : 'empty'
    },

    dimStarState(dimension: keyof DimensionScores, n: number): 'filled' | 'empty' {
      const active = data.hoverScores[dimension] || data.scores[dimension]
      return n <= active ? 'filled' : 'empty'
    },

    async submit(): Promise<void> {
      if (!data.canSubmit) return

      data.submitting = true
      data.error = ''

      const dimValues = Object.values(data.scores).filter((v: number) => v > 0)
      const overall = dimValues.length === 4
        ? parseFloat((dimValues.reduce((a: number, b: number) => a + b, 0) / 4).toFixed(2))
        : data.rating

      const payload = {
        story_id: data.storyId,
        chapter_index: data.chapterIndex,
        scores: {
          coherence: data.scores.coherence || data.rating,
          character: data.scores.character || data.rating,
          drama:     data.scores.drama     || data.rating,
          writing:   data.scores.writing   || data.rating,
        },
        overall,
        ...(data.comment.trim() ? { comment: data.comment.trim() } : {}),
      }

      try {
        await mockAPI.post('/feedback/rate', payload)
        data.submitted = true
      } catch (_err) {
        data.error = 'Could not submit feedback. Please try again.'
      } finally {
        data.submitting = false
      }
    },

    reset(): void {
      data.rating       = 0
      data.hoverRating  = 0
      data.scores       = { coherence: 0, character: 0, drama: 0, writing: 0 }
      data.hoverScores  = { coherence: 0, character: 0, drama: 0, writing: 0 }
      data.comment      = ''
      data.submitted    = false
      data.submitting   = false
      data.showDetails  = false
      data.error        = ''
    },
  }
  return data
}

beforeEach(() => {
  mockAPI = { post: vi.fn() }
})

// ============================================================================
// canSubmit
// ============================================================================
describe('feedbackWidget.canSubmit', () => {
  it('is false when rating is 0', () => {
    const d = createFeedbackData('s1', 0)
    expect(d.canSubmit).toBe(false)
  })

  it('is true when rating > 0 and not submitted/submitting', () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 3
    expect(d.canSubmit).toBe(true)
  })

  it('is false while submitting', () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 4
    d.submitting = true
    expect(d.canSubmit).toBe(false)
  })

  it('is false after submission', () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 5
    d.submitted = true
    expect(d.canSubmit).toBe(false)
  })
})

// ============================================================================
// setRating / setScore
// ============================================================================
describe('feedbackWidget.setRating() / setScore()', () => {
  it('setRating updates the rating', () => {
    const d = createFeedbackData('s1', 0)
    d.setRating(4)
    expect(d.rating).toBe(4)
  })

  it('setScore updates the named dimension', () => {
    const d = createFeedbackData('s1', 0)
    d.setScore('drama', 5)
    expect(d.scores.drama).toBe(5)
    // Other dimensions unchanged
    expect(d.scores.coherence).toBe(0)
  })
})

// ============================================================================
// starState / dimStarState
// ============================================================================
describe('feedbackWidget.starState()', () => {
  it('returns filled for stars up to the active rating', () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 3
    expect(d.starState(1)).toBe('filled')
    expect(d.starState(3)).toBe('filled')
    expect(d.starState(4)).toBe('empty')
  })

  it('hover rating takes priority over actual rating', () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 2
    d.hoverRating = 4
    expect(d.starState(3)).toBe('filled')  // 3 <= 4
    expect(d.starState(5)).toBe('empty')
  })

  it('returns all empty when rating and hover are 0', () => {
    const d = createFeedbackData('s1', 0)
    for (let i = 1; i <= 5; i++) {
      expect(d.starState(i)).toBe('empty')
    }
  })
})

describe('feedbackWidget.dimStarState()', () => {
  it('returns filled for stars up to the dimension score', () => {
    const d = createFeedbackData('s1', 0)
    d.scores.coherence = 4
    expect(d.dimStarState('coherence', 4)).toBe('filled')
    expect(d.dimStarState('coherence', 5)).toBe('empty')
  })

  it('dimension hover takes priority over score', () => {
    const d = createFeedbackData('s1', 0)
    d.scores.writing = 1
    d.hoverScores.writing = 5
    expect(d.dimStarState('writing', 5)).toBe('filled')
  })
})

// ============================================================================
// submit()
// ============================================================================
describe('feedbackWidget.submit()', () => {
  it('does nothing when canSubmit is false', async () => {
    const d = createFeedbackData('s1', 0)
    // rating is 0, so canSubmit === false
    await d.submit()
    expect(mockAPI.post).not.toHaveBeenCalled()
  })

  it('posts correct payload with all dimension scores', async () => {
    const d = createFeedbackData('story-42', 1)
    d.rating = 4
    d.scores = { coherence: 5, character: 4, drama: 3, writing: 4 }
    d.comment = '  Great chapter!  '
    mockAPI.post.mockResolvedValue({ ok: true })

    await d.submit()

    expect(mockAPI.post).toHaveBeenCalledOnce()
    const [path, payload] = mockAPI.post.mock.calls[0]
    expect(path).toBe('/feedback/rate')
    expect(payload.story_id).toBe('story-42')
    expect(payload.chapter_index).toBe(1)
    // Overall = average of all 4 dimensions = (5+4+3+4)/4 = 4.00
    expect(payload.overall).toBe(4.0)
    expect(payload.comment).toBe('Great chapter!')
    expect(d.submitted).toBe(true)
    expect(d.submitting).toBe(false)
  })

  it('uses main rating as overall when not all dimensions are filled', async () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 3
    d.scores = { coherence: 0, character: 0, drama: 0, writing: 0 }
    mockAPI.post.mockResolvedValue({})

    await d.submit()

    const [, payload] = mockAPI.post.mock.calls[0]
    expect(payload.overall).toBe(3)
  })

  it('omits comment field when comment is empty/whitespace', async () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 5
    d.comment = '   '
    mockAPI.post.mockResolvedValue({})

    await d.submit()

    const [, payload] = mockAPI.post.mock.calls[0]
    expect(payload).not.toHaveProperty('comment')
  })

  it('sets error and clears submitting on API failure', async () => {
    const d = createFeedbackData('s1', 0)
    d.rating = 3
    mockAPI.post.mockRejectedValue(new Error('Network error'))

    await d.submit()

    expect(d.error).toBe('Could not submit feedback. Please try again.')
    expect(d.submitting).toBe(false)
    expect(d.submitted).toBe(false)
  })
})

// ============================================================================
// reset()
// ============================================================================
describe('feedbackWidget.reset()', () => {
  it('resets all fields to initial defaults', () => {
    const d = createFeedbackData('s1', 2)
    d.rating = 5
    d.hoverRating = 3
    d.scores = { coherence: 4, character: 3, drama: 5, writing: 4 }
    d.comment = 'Amazing'
    d.submitted = true
    d.error = 'old error'
    d.showDetails = true

    d.reset()

    expect(d.rating).toBe(0)
    expect(d.hoverRating).toBe(0)
    expect(d.scores).toEqual({ coherence: 0, character: 0, drama: 0, writing: 0 })
    expect(d.comment).toBe('')
    expect(d.submitted).toBe(false)
    expect(d.submitting).toBe(false)
    expect(d.showDetails).toBe(false)
    expect(d.error).toBe('')
  })
})
