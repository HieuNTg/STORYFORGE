# Sprint 11: AI & UX Polish (Open Source)
**Duration:** 1 week | **Owner:** AI/ML + Frontend | **Priority:** MEDIUM

## Objectives
- AI scoring calibration with user feedback
- LLM cost optimization (prompt caching, structured outputs)
- UX accessibility & polish
- Plugin/extension architecture for community contributions

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

### 11.2 LLM Optimization [Backend] — 2 days
- [ ] Implement provider prompt caching:
  - OpenAI: system prompt caching
  - Anthropic: prompt caching beta
  - Measure cache hit rates and cost savings
- [ ] Migrate to Structured Outputs:
  - Replace `generate_json()` regex parsing
  - Use native JSON mode where supported
  - Fallback for providers without structured output
- [ ] Optimize prompt templates:
  - Reduce token count in system prompts
  - Share common prefixes across layers

### 11.3 UX Polish [Frontend] — 2 days
- [ ] Accessibility audit (WCAG 2.1 AA):
  - Add aria labels to interactive elements
  - Keyboard navigation support
  - Color contrast verification
- [ ] State persistence:
  - Save form state to localStorage
  - Restore on page refresh
- [ ] Dark mode support:
  - CSS variables for theme colors
  - Toggle in UI header
  - Persist preference to localStorage
- [ ] i18n improvements:
  - Extract any hardcoded strings
  - Verify locale switching works
  - Community translation guide

### 11.4 Plugin Architecture [Backend] — 1 day
- [ ] Create `plugins/` directory with README:
  - Plugin interface definition
  - Example plugin (custom genre rules)
  - Loading mechanism in orchestrator
- [ ] Document how to add:
  - Custom LLM providers
  - Custom export formats
  - Custom genre drama rules
  - Custom TTS providers

## Success Criteria
- [ ] Scoring calibration improves correlation to r > 0.7
- [ ] Prompt caching reduces cost by > 20%
- [ ] WCAG 2.1 AA compliance on core flows
- [ ] Dark mode toggle works
- [ ] Plugin example works end-to-end
