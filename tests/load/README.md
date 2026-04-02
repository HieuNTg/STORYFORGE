# StoryForge Load Tests

Locust-based load and performance tests for the StoryForge API.

## Installation

```bash
pip install locust
# or install all test dependencies at once:
pip install -r requirements-test.txt
```

## Running Tests

### Quick smoke test (10 users, 30 seconds)

```bash
./tests/load/run-load-test.sh -u 10 -r 2 -t 30s -T smoke
```

### Default load test (50 users, 2 minutes)

```bash
./tests/load/run-load-test.sh
```

### Full soak test (100 users, 10 minutes, against staging)

```bash
./tests/load/run-load-test.sh -u 100 -r 10 -t 10m -H http://staging.example.com
```

### Interactive Locust web UI (manual control)

```bash
locust -f tests/load/locustfile.py --host http://localhost:7860
# Open http://localhost:8089 in your browser
```

### Run a specific user class only

```bash
# Only health checks
./tests/load/run-load-test.sh -c HealthCheckUser -u 20 -t 1m

# Only config operations
./tests/load/run-load-test.sh -c ConfigUser -u 30 -t 2m

# Realistic mixed traffic (default)
./tests/load/run-load-test.sh -c MixedUser
```

### Filter by task tags

```bash
# Smoke tags only
locust -f tests/load/locustfile.py --headless -u 5 -r 1 -t 30s \
    --host http://localhost:7860 --tags smoke

# All read-only tags (safe for CI)
locust -f tests/load/locustfile.py --headless -u 10 -r 2 -t 1m \
    --host http://localhost:7860 --tags read
```

## User Classes

| Class | Weight | Wait time | Purpose |
|---|---|---|---|
| `HealthCheckUser` | 3 | 0.5-1.5s | High-rate smoke test on `/api/health` |
| `ConfigUser` | 4 | 1-3s | Read-heavy config operations |
| `PipelineUser` | 1 | 10-30s | Expensive pipeline runs (throttled) |
| `ExportUser` | 2 | 5-15s | Export endpoint availability |
| `MixedUser` | 5 | 1-4s | Realistic 70/20/10 traffic mix |

## Reports

HTML and CSV reports are saved to `tests/load/reports/` with a timestamp prefix.

```
tests/load/reports/
  20260402_143000.html          # Visual Locust report
  20260402_143000_stats.csv     # Per-endpoint stats
  20260402_143000_failures.csv  # Failure details (if any)
```

Open the `.html` file in a browser for charts and a full breakdown.

## Interpreting Results

### Key metrics

- **RPS** (requests/second) — throughput; compare against baseline after changes
- **p50 / median** — typical user experience
- **p95** — 95% of requests complete within this time; primary SLO target
- **p99** — tail latency; flags worst-case outliers
- **Failure rate** — anything above 1% warrants investigation

### Baseline targets

| Endpoint type | p50 target | p95 target | Notes |
|---|---|---|---|
| Health check (`/api/health`) | < 50ms | < 100ms | Must never exceed 200ms |
| Config reads (`GET /api/config`) | < 100ms | < 300ms | Includes JSON serialisation |
| Config writes (`PUT /api/config`) | < 200ms | < 500ms | Disk write included |
| Pipeline genres/templates | < 150ms | < 400ms | Static data |
| Pipeline start (`POST /api/pipeline/run`) | < 2s | < 5s | SSE stream initiation only |
| Export endpoints | < 500ms | < 2s | File generation varies |

### Failure rate thresholds

- **< 0.1%** — excellent
- **0.1% – 1%** — acceptable under load
- **> 1%** — investigate; likely capacity or bug issue
- **> 5%** — failing SLO; block deployment

### Common issues

**High p99 on `/api/config`**
Check disk I/O on the host — config writes flush to `config.json` synchronously.

**Pipeline start timeout**
The `PipelineUser` sends a real pipeline request. Ensure `enable_agents=False` and
`enable_media=False` are set (they are by default in the locustfile) to keep latency
bounded. If the LLM API is not configured, requests will fail fast with a validation
error — this is expected in CI environments.

**Locust `OSError: [Errno 24] Too many open files`**
Increase the OS file descriptor limit before running:
```bash
ulimit -n 65536
./tests/load/run-load-test.sh -u 200
```
