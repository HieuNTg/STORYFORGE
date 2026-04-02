# Sprint 11: AI & UX Polish
**Duration:** 1 week | **Owner:** AI/ML + Frontend | **Priority:** MEDIUM

## Objectives
- AI scoring calibration with user feedback
- Provider-level prompt caching
- Structured outputs migration
- UX polish and accessibility

## Tasks

### 11.1 Scoring Calibration [AI/ML] — 2 days
- [ ] Analyze user feedback vs LLM scores:
  - Correlation analysis per genre
  - Identify systematic biases
  - Create calibration mapping function
- [ ] Update `services/quality_scorer.py`:
  - Apply calibration curves
  - Genre-specific scoring adjustments
  - Log score deltas for ongoing monitoring
- [ ] Improve prompt injection detection:
  - Add LLM-based secondary check for flagged inputs
  - Reduce false positive rate

### 11.2 LLM Cost Optimization [Backend + Tech R&D] — 2 days
- [ ] Implement provider prompt caching:
  - OpenAI: system prompt caching
  - Anthropic: prompt caching beta
  - Measure cache hit rates and cost savings
- [ ] Migrate to Structured Outputs:
  - Replace `generate_json()` regex parsing
  - Use OpenAI `response_format={"type": "json_schema"}`
  - Fallback for providers without structured output
- [ ] Optimize prompt templates:
  - Reduce token count in system prompts
  - Share common prefixes across layers
  - Measure token savings

### 11.3 UX Polish [Frontend] — 2 days
- [ ] Accessibility audit (WCAG 2.1 AA):
  - Add aria labels to interactive elements
  - Keyboard navigation support
  - Color contrast verification
  - Screen reader testing
- [ ] State persistence:
  - Save form state to localStorage
  - Restore on page refresh
  - Clear on successful submission
- [ ] Error boundary improvements:
  - Graceful degradation for JS errors
  - Retry buttons for failed API calls
  - Offline detection and notification
- [ ] i18n expansion prep:
  - Extract any hardcoded strings
  - Verify locale switching works

### 11.4 Character Consistency [AI/ML] — 1 day
- [ ] Improve rolling context window:
  - Increase character detail retention
  - Add character summary refresh every N chapters
  - Track character appearance descriptions for image consistency

## Success Criteria
- [ ] Scoring calibration improves correlation to r > 0.7
- [ ] Prompt caching reduces cost by > 20%
- [ ] Structured outputs reduce JSON parse errors by > 90%
- [ ] WCAG 2.1 AA compliance on core flows
