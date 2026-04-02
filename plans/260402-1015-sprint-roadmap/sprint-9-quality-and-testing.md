# Sprint 9: Quality & Testing
**Duration:** 1 week | **Owner:** QA + AI/ML | **Priority:** HIGH

## Objectives
- Code coverage reporting & enforcement
- Load/performance testing
- AI quality evaluation benchmark
- Redis-backed rate limiting

## Tasks

### 9.1 Coverage Reporting [QA] — 1 day
- [ ] Add `pytest-cov` to requirements.txt
- [ ] Configure coverage in `pyproject.toml`:
  - Source: pipeline/, services/, api/, middleware/
  - Exclude: tests/, scripts/, __pycache__
  - Minimum coverage threshold: 70%
  - Report formats: terminal, HTML, XML (for CI)
- [ ] Update `.github/workflows/ci.yml`:
  - Add `--cov` flag to pytest
  - Upload coverage report as artifact
  - Add coverage badge to README
- [ ] Identify uncovered critical paths and create test backlog

### 9.2 Load & Performance Testing [QA + DevOps] — 2 days
- [ ] Create `tests/load/locustfile.py`:
  - Scenario 1: Concurrent config reads (100 users)
  - Scenario 2: Concurrent pipeline starts (10 users)
  - Scenario 3: Mixed API traffic (read:write 80:20)
  - Scenario 4: SSE streaming stability (50 connections)
- [ ] Create `tests/load/run-load-test.sh`:
  - Headless Locust execution with HTML report
  - Configurable user count, spawn rate, duration
- [ ] Establish performance baselines:
  - API response time p50, p95, p99
  - Pipeline execution time per layer
  - Max concurrent users before degradation
  - Memory/CPU usage under load

### 9.3 AI Evaluation Benchmark [AI/ML] — 3 days
- [ ] Create `tests/benchmarks/golden_dataset.json`:
  - 20 story prompts across 5 genres
  - Human-annotated quality scores (1-5 scale)
  - Expected character consistency markers
  - Expected plot coherence checkpoints
- [ ] Create `tests/benchmarks/eval_runner.py`:
  - Run pipeline on golden dataset
  - Compare LLM quality scores vs human scores
  - Calculate correlation coefficient (target: r > 0.7)
  - Generate deviation report
- [ ] Create `tests/benchmarks/scoring_calibration.py`:
  - Analyze score distribution per model
  - Detect scoring bias (too lenient / too harsh)
  - Generate calibration curves
- [ ] Document benchmark methodology in `docs/ai-evaluation.md`

### 9.4 Redis Rate Limiter [Backend] — 1 day
- [ ] Create `services/rate_limiter_redis.py`:
  - Redis-backed sliding window rate limiting
  - Fallback to in-memory if Redis unavailable
  - Interface compatible with current rate limiter
- [ ] Update `middleware/rate_limiter.py`:
  - Abstract rate limiter interface
  - Auto-detect Redis availability
  - Graceful degradation to in-memory
- [ ] Add Redis to docker-compose.production.yml

## Success Criteria
- [ ] Coverage report generates in CI, threshold enforced
- [ ] Load test report shows max concurrent capacity
- [ ] Golden dataset created with 20+ annotated examples
- [ ] Scoring correlation r > 0.6 (stretch: r > 0.7)
- [ ] Rate limiter persists across server restarts (Redis mode)
