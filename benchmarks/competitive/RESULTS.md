# Competitive Benchmark Results

**Generated:** 2026-05-25T10:06:34+00:00  
**Config:** 10s × 64 connections × 4 wrk threads  
**Server:** Granian (1 worker, ASGI)  
**Tool:** wrk

## Summary — Throughput (Requests/sec, higher is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 17,035 | 8,878 | 24,857 🏆 | 12,315 | 13,739 | 20,307 |
| json | 45,734 | 18,021 | 46,539 🏆 | 20,920 | 19,092 | 40,400 |
| path_param | 42,809 | 13,229 | 44,087 🏆 | 17,897 | 18,421 | 35,992 |
| plaintext | 56,317 | 17,730 | 61,804 🏆 | 23,086 | 21,874 | 44,216 |
| query_params | 29,189 | 14,337 | 31,691 🏆 | 18,104 | 15,836 | 27,347 |
| routing_stress | 44,327 | 9,043 | 46,247 🏆 | 21,811 | 17,320 | 12,338 |

## p99 Latency (ms, lower is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 4.62 | 22.07 | 3.07 🏆 | 7.36 | 15.80 | 4.30 |
| json | 1.84 | 4.71 | 1.77 🏆 | 3.79 | 4.19 | 1.94 |
| path_param | 1.88 🏆 | 6.43 | 1.89 | 4.59 | 4.36 | 2.14 |
| plaintext | 1.64 | 4.51 | 1.35 🏆 | 3.33 | 4.96 | 1.78 |
| query_params | 2.69 | 7.49 | 2.41 🏆 | 4.50 | 5.35 | 2.78 |
| routing_stress | 2.12 | 9.53 | 1.71 🏆 | 3.68 | 11.65 | 6.99 |

## Detailed Results

### body_validation

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 24,857 | 2.56 | 2.59 | 2.85 | 3.07 | 0 |
| starlette | 20,307 | 3.17 | 3.12 | 3.59 | 4.30 | 0 |
| blacksheep | 17,035 | 3.73 | 3.70 | 4.32 | 4.62 | 0 |
| sanic | 13,739 | 4.79 | 4.36 | 5.67 | 15.80 | 0 |
| litestar | 12,315 | 5.27 | 4.85 | 6.53 | 7.36 | 0 |
| fastapi | 8,878 | 7.37 | 6.85 | 9.01 | 22.07 | 0 |

### json

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 46,539 | 1.36 | 1.38 | 1.55 | 1.77 | 0 |
| blacksheep | 45,734 | 1.39 | 1.40 | 1.59 | 1.84 | 0 |
| starlette | 40,400 | 1.58 | 1.58 | 1.77 | 1.94 | 0 |
| litestar | 20,920 | 3.04 | 3.14 | 3.44 | 3.79 | 0 |
| sanic | 19,092 | 3.37 | 3.35 | 3.88 | 4.19 | 0 |
| fastapi | 18,021 | 3.55 | 3.36 | 4.30 | 4.71 | 0 |

### path_param

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 44,087 | 1.44 | 1.45 | 1.62 | 1.89 | 0 |
| blacksheep | 42,809 | 1.48 | 1.49 | 1.69 | 1.88 | 0 |
| starlette | 35,992 | 1.77 | 1.78 | 1.97 | 2.14 | 0 |
| sanic | 18,421 | 3.48 | 3.48 | 4.01 | 4.36 | 0 |
| litestar | 17,897 | 3.55 | 3.85 | 4.26 | 4.59 | 0 |
| fastapi | 13,229 | 4.83 | 4.84 | 6.16 | 6.43 | 0 |

### plaintext

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 61,804 | 1.03 | 1.02 | 1.18 | 1.35 | 0 |
| blacksheep | 56,317 | 1.13 | 1.13 | 1.32 | 1.64 | 0 |
| starlette | 44,216 | 1.44 | 1.45 | 1.62 | 1.78 | 0 |
| litestar | 23,086 | 2.75 | 2.82 | 3.11 | 3.33 | 0 |
| sanic | 21,874 | 2.92 | 2.87 | 3.36 | 4.96 | 0 |
| fastapi | 17,730 | 3.61 | 3.51 | 4.28 | 4.51 | 0 |

### query_params

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 31,691 | 2.00 | 2.02 | 2.24 | 2.41 | 0 |
| blacksheep | 29,189 | 2.17 | 2.20 | 2.47 | 2.69 | 0 |
| starlette | 27,347 | 2.34 | 2.34 | 2.59 | 2.78 | 0 |
| litestar | 18,104 | 3.51 | 3.35 | 4.31 | 4.50 | 0 |
| sanic | 15,836 | 4.05 | 3.92 | 5.00 | 5.35 | 0 |
| fastapi | 14,337 | 4.46 | 3.92 | 7.02 | 7.49 | 0 |

### routing_stress

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 46,247 | 1.38 | 1.39 | 1.55 | 1.71 | 0 |
| blacksheep | 44,327 | 1.44 | 1.44 | 1.65 | 2.12 | 0 |
| litestar | 21,811 | 2.93 | 3.00 | 3.32 | 3.68 | 0 |
| sanic | 17,320 | 3.76 | 3.54 | 4.62 | 11.65 | 0 |
| starlette | 12,338 | 5.18 | 5.14 | 6.75 | 6.99 | 0 |
| fastapi | 9,043 | 7.07 | 6.64 | 9.23 | 9.53 | 0 |


## How HawkAPI Ranks

HawkAPI placement per scenario:

- body_validation: #1
- json: #1
- path_param: #1
- plaintext: #1
- query_params: #1
- routing_stress: #1
