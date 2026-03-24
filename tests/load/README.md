# Load Tests

Load tests for the ARCHITECT system using [k6](https://k6.io/).

## Prerequisites

- [k6](https://k6.io/docs/get-started/installation/) installed
- ARCHITECT services running (`make run-all`)
- API key configured if auth is enabled

## Running

```bash
# Basic smoke test (10 VUs, 30s)
k6 run tests/load/smoke.js

# Load test (50 VUs, 5m)
k6 run tests/load/load.js

# Stress test (100 VUs, 10m)
k6 run tests/load/stress.js
```

## Interpreting Results

- **http_req_duration p95 < 500ms** — acceptable for API endpoints
- **http_req_failed < 1%** — error rate threshold
- **http_reqs** — throughput (requests/second)
