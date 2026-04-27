# Competitive Benchmark Results

**Generated:** 2026-04-27T07:02:54+00:00  
**Config:** 10s × 64 connections × 4 wrk threads  
**Server:** Granian (1 worker, ASGI)  
**Tool:** wrk

## Summary — Throughput (Requests/sec, higher is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 13,185 | 7,104 | 21,700 🏆 | 8,903 | 10,960 | 17,769 |
| json | 32,296 | 11,994 | 36,725 🏆 | 14,551 | 12,649 | 30,435 |
| path_param | 29,501 | 9,340 | 33,282 🏆 | 12,920 | 13,177 | 25,363 |
| plaintext | 45,926 | 12,367 | 49,639 🏆 | 14,610 | 13,744 | 35,775 |
| query_params | 17,633 | 9,112 | 21,288 🏆 | 12,083 | 10,604 | 16,708 |
| routing_stress | 32,552 | 6,787 | 37,051 🏆 | 13,955 | 14,270 | 9,627 |

## p99 Latency (ms, lower is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 6.39 | 13.96 | 3.88 🏆 | 9.95 | 12.23 | 5.40 |
| json | 2.72 | 6.28 | 2.43 🏆 | 5.24 | 5.93 | 2.65 |
| path_param | 2.77 | 8.37 | 2.66 🏆 | 5.85 | 5.88 | 3.13 |
| plaintext | 2.34 | 6.28 | 2.28 | 5.01 | 5.41 | 2.24 🏆 |
| query_params | 4.36 | 9.52 | 3.67 🏆 | 6.17 | 7.30 | 4.45 |
| routing_stress | 2.53 | 11.84 | 2.19 🏆 | 5.31 | 11.65 | 8.16 |

## Detailed Results

### body_validation

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 21,700 | 2.92 | 2.89 | 3.47 | 3.88 | 0 |
| starlette | 17,769 | 3.58 | 3.47 | 4.42 | 5.40 | 0 |
| blacksheep | 13,185 | 4.82 | 4.61 | 5.94 | 6.39 | 0 |
| sanic | 10,960 | 5.89 | 5.40 | 7.64 | 12.23 | 0 |
| litestar | 8,903 | 7.19 | 6.65 | 8.92 | 9.95 | 0 |
| fastapi | 7,104 | 9.03 | 8.67 | 11.04 | 13.96 | 0 |

### json

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 36,725 | 1.72 | 1.75 | 2.01 | 2.43 | 0 |
| blacksheep | 32,296 | 1.98 | 2.01 | 2.28 | 2.72 | 0 |
| starlette | 30,435 | 2.08 | 2.09 | 2.42 | 2.65 | 0 |
| litestar | 14,551 | 4.36 | 4.66 | 5.00 | 5.24 | 0 |
| sanic | 12,649 | 5.06 | 5.15 | 5.67 | 5.93 | 0 |
| fastapi | 11,994 | 5.31 | 5.52 | 6.08 | 6.28 | 0 |

### path_param

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 33,282 | 1.91 | 1.93 | 2.22 | 2.66 | 0 |
| blacksheep | 29,501 | 2.15 | 2.16 | 2.52 | 2.77 | 0 |
| starlette | 25,363 | 2.52 | 2.51 | 2.92 | 3.13 | 0 |
| sanic | 13,177 | 4.83 | 4.96 | 5.60 | 5.88 | 0 |
| litestar | 12,920 | 4.95 | 5.23 | 5.61 | 5.85 | 0 |
| fastapi | 9,340 | 6.80 | 7.01 | 8.14 | 8.37 | 0 |

### plaintext

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 49,639 | 1.28 | 1.25 | 1.53 | 2.28 | 0 |
| blacksheep | 45,926 | 1.38 | 1.38 | 1.65 | 2.34 | 0 |
| starlette | 35,775 | 1.78 | 1.80 | 2.04 | 2.24 | 0 |
| litestar | 14,610 | 4.35 | 4.57 | 4.82 | 5.01 | 0 |
| sanic | 13,744 | 4.63 | 4.71 | 5.15 | 5.41 | 0 |
| fastapi | 12,367 | 5.17 | 5.35 | 6.07 | 6.28 | 0 |

### query_params

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 21,288 | 2.98 | 3.00 | 3.45 | 3.67 | 0 |
| blacksheep | 17,633 | 3.61 | 3.77 | 4.04 | 4.36 | 0 |
| starlette | 16,708 | 3.80 | 3.94 | 4.19 | 4.45 | 0 |
| litestar | 12,083 | 5.29 | 5.62 | 5.98 | 6.17 | 0 |
| sanic | 10,604 | 6.00 | 6.16 | 6.90 | 7.30 | 0 |
| fastapi | 9,112 | 7.02 | 6.57 | 9.33 | 9.52 | 0 |

### routing_stress

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 37,051 | 1.72 | 1.74 | 1.98 | 2.19 | 0 |
| blacksheep | 32,552 | 1.95 | 1.96 | 2.29 | 2.53 | 0 |
| sanic | 14,270 | 4.55 | 4.13 | 6.07 | 11.65 | 0 |
| litestar | 13,955 | 4.56 | 4.80 | 5.08 | 5.31 | 0 |
| starlette | 9,627 | 6.64 | 6.61 | 8.01 | 8.16 | 0 |
| fastapi | 6,787 | 9.35 | 10.00 | 11.51 | 11.84 | 0 |


## How HawkAPI Ranks

HawkAPI placement per scenario:

- body_validation: #1
- json: #1
- path_param: #1
- plaintext: #1
- query_params: #1
- routing_stress: #1
