# Sprint 10: Business Layer
**Duration:** 1 week | **Owner:** Backend + Frontend + PM | **Priority:** HIGH

## Objectives
- Payment/billing integration (Stripe)
- Landing page for marketing
- Onboarding flow redesign
- User feedback system

## Tasks

### 10.1 Billing Integration [Backend] — 3 days
- [ ] Create `services/billing/`:
  - `stripe_client.py` — Stripe API wrapper
  - `subscription_manager.py` — plan management
  - `usage_tracker.py` — token/story usage metering
  - `webhook_handler.py` — Stripe webhook processing
- [ ] Create `api/v1/billing_routes.py`:
  - POST /subscribe — create subscription
  - GET /subscription — current plan status
  - POST /webhook/stripe — webhook receiver
  - GET /usage — current period usage
- [ ] Define pricing tiers:
  - Free: 3 stories/month, basic features
  - Pro ($19/mo): unlimited stories, quality gate, TTS
  - Enterprise ($99/mo): all features, priority support, API access
- [ ] Create `models/billing.py` — Pydantic schemas
- [ ] Add billing tables to PostgreSQL schema

### 10.2 Landing Page [Frontend] — 2 days
- [ ] Create `web/landing/index.html`:
  - Hero section with value proposition
  - Feature showcase (3-layer pipeline visual)
  - Pricing table with tier comparison
  - Social proof / demo section
  - CTA to sign up / try demo
- [ ] Create `web/landing/demo.html`:
  - Pre-generated story examples
  - Interactive pipeline visualization
  - "Try it free" flow → sign up

### 10.3 Onboarding Redesign [Frontend + Backend] — 1 day
- [ ] Redesign onboarding wizard:
  - Step 1: Choose plan (Free starts immediately)
  - Step 2: Select genre preference
  - Step 3: First story generation (guided)
  - Skip API key config for free tier (use shared key with rate limits)
- [ ] Create `web/js/onboarding-v2.js`
- [ ] Update `api/v1/onboarding_routes.py`

### 10.4 User Feedback System [AI/ML + Frontend] — 1 day
- [ ] Create `api/v1/feedback_routes.py`:
  - POST /feedback/story — rate story (1-5 stars + optional text)
  - POST /feedback/chapter — rate individual chapter
  - GET /feedback/stats — aggregate feedback data
- [ ] Create `services/feedback_collector.py`:
  - Store ratings in PostgreSQL
  - Aggregate for AI scoring calibration
  - Export for benchmark updates
- [ ] Add rating UI in story reader view
- [ ] Add "Report issue" button per chapter

## Success Criteria
- [ ] Stripe checkout flow works end-to-end (test mode)
- [ ] Landing page scores > 80 on Lighthouse
- [ ] New user can generate first story in < 3 minutes
- [ ] Feedback ratings stored and queryable
