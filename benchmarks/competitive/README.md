# Competitive Benchmark Suite

Compares HawkAPI throughput and latency against top Python web frameworks under
identical conditions: same ASGI server (Granian), same load tool (wrk), same
endpoints, same payloads.

## Frameworks Tested

| ID | Framework | Install |
|---|---|---|
| `hawkapi` | HawkAPI | local source |
| `fastapi` | FastAPI | `pip install fastapi` |
| `litestar` | Litestar | `pip install litestar` |
| `blacksheep` | BlackSheep | `pip install blacksheep` |
| `starlette` | Starlette | `pip install starlette` |
| `sanic` | Sanic (ASGI mode) | `pip install sanic` |

## Scenarios

| Name | Method | Path | Description |
|---|---|---|---|
| `json` | GET | `/json` | Minimal JSON response |
| `plaintext` | GET | `/plaintext` | text/plain response |
| `path_param` | GET | `/users/42` | Path param coercion to int |
| `body_validation` | POST | `/items` | JSON body decoded into Struct/Model |
| `query_params` | GET | `/search?q=hello&limit=20` | Query string parsing |
| `routing_stress` | GET | `/route/87` | Lookup with 100 registered routes |

All apps register **identical endpoint surface** so any difference reflects
framework overhead, not workload.

## Prerequisites

```bash
# wrk (macOS)
brew install wrk

# Framework deps (use the bench extra)
uv sync --extra bench
```

## Running

```bash
# Default: all frameworks, all scenarios, 10s × 64 connections
./benchmarks/competitive/run_all.sh

# Override duration and concurrency
DURATION=30 CONNECTIONS=128 ./benchmarks/competitive/run_all.sh

# Single framework
uv run python benchmarks/competitive/runner.py --framework hawkapi

# Single scenario
uv run python benchmarks/competitive/runner.py --scenario json
```

Results are written to:

- `benchmarks/competitive/results/{framework}_{scenario}.json` — per run
- `benchmarks/competitive/results/summary.json` — combined run summary
- `benchmarks/competitive/RESULTS.md` — human-readable report

## Methodology

- Single Granian worker per framework (no multi-process inflation)
- 4 wrk threads, 64 keep-alive connections, 10 seconds (defaults)
- 20-request curl warm-up before each measured run
- Server is restarted between scenarios for a clean state
- Errors (non-2xx/3xx) are reported per scenario

## Caveats

- Single-machine runs — fine for relative comparison, not absolute
- Granian itself adds overhead identical across frameworks (constant baseline)
- Sanic runs in ASGI mode for fairness; its native server may be faster
- Cold-start, memory, and concurrent-load benchmarks live in `benchmarks/`
  separately
