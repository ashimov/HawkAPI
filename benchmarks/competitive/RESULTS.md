# Competitive Benchmark Results

**Generated:** 2026-04-17T18:59:28+00:00  
**Config:** 10s × 64 connections × 4 wrk threads  
**Server:** Granian (1 worker, ASGI)  
**Tool:** wrk

## Summary — Throughput (Requests/sec, higher is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 46,418 | 23,628 | 82,202 🏆 | 31,290 | 34,978 | 49,247 |
| json | 125,503 | 44,852 | 126,820 🏆 | 55,507 | 51,110 | 92,766 |
| path_param | 114,354 | 33,436 | 144,704 🏆 | 49,928 | 51,258 | 84,670 |
| plaintext | 165,151 🏆 | 44,276 | 148,103 | 56,580 | 55,624 | 106,698 |
| query_params | 74,526 | 25,710 | 90,221 🏆 | 48,828 | 42,798 | 63,832 |
| routing_stress | 121,214 | 17,123 | 134,356 🏆 | 56,085 | 42,801 | 27,397 |

## p99 Latency (ms, lower is better)

| Scenario | blacksheep | fastapi | hawkapi | litestar | sanic | starlette |
|---|---|---|---|---|---|---|
| body_validation | 4.31 | 7.75 | 1.09 🏆 | 2.64 | 5.25 | 1.87 |
| json | 0.61 🏆 | 4.57 | 2.71 | 1.69 | 2.59 | 1.38 |
| path_param | 0.67 | 2.11 | 0.56 🏆 | 1.41 | 1.54 | 1.68 |
| plaintext | 0.74 🏆 | 3.48 | 1.11 | 1.98 | 2.13 | 1.23 |
| query_params | 0.96 🏆 | 2.76 | 3.13 | 1.42 | 2.25 | 2.18 |
| routing_stress | 0.96 🏆 | 4.93 | 2.06 | 1.24 | 3.66 | 2.51 |

## Detailed Results

### body_validation

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 82,202 | 0.77 | 0.76 | 0.84 | 1.09 | 0 |
| starlette | 49,247 | 1.31 | 1.30 | 1.39 | 1.87 | 0 |
| blacksheep | 46,418 | 1.45 | 1.34 | 1.46 | 4.31 | 0 |
| sanic | 34,978 | 1.85 | 1.75 | 2.01 | 5.25 | 0 |
| litestar | 31,290 | 2.07 | 2.01 | 2.16 | 2.64 | 0 |
| fastapi | 23,628 | 2.74 | 2.63 | 2.83 | 7.75 | 0 |

### json

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 126,820 | 0.56 | 0.42 | 0.81 | 2.71 | 0 |
| blacksheep | 125,503 | 0.51 | 0.51 | 0.54 | 0.61 | 0 |
| starlette | 92,766 | 0.70 | 0.68 | 0.72 | 1.38 | 0 |
| litestar | 55,507 | 1.16 | 1.14 | 1.18 | 1.69 | 0 |
| sanic | 51,110 | 1.26 | 1.28 | 1.35 | 2.59 | 0 |
| fastapi | 44,852 | 1.48 | 1.36 | 1.52 | 4.57 | 0 |

### path_param

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 144,704 | 0.44 | 0.43 | 0.47 | 0.56 | 0 |
| blacksheep | 114,354 | 0.56 | 0.56 | 0.59 | 0.67 | 0 |
| starlette | 84,670 | 0.78 | 0.74 | 0.78 | 1.68 | 0 |
| sanic | 51,258 | 1.26 | 1.29 | 1.35 | 1.54 | 0 |
| litestar | 49,928 | 1.29 | 1.27 | 1.31 | 1.41 | 0 |
| fastapi | 33,436 | 1.91 | 1.91 | 1.96 | 2.11 | 0 |

### plaintext

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| blacksheep | 165,151 | 0.38 | 0.37 | 0.43 | 0.74 | 0 |
| hawkapi | 148,103 | 0.43 | 0.41 | 0.48 | 1.11 | 0 |
| starlette | 106,698 | 0.61 | 0.58 | 0.63 | 1.23 | 0 |
| litestar | 56,580 | 1.14 | 1.11 | 1.19 | 1.98 | 0 |
| sanic | 55,624 | 1.17 | 1.20 | 1.27 | 2.13 | 0 |
| fastapi | 44,276 | 1.47 | 1.39 | 1.56 | 3.48 | 0 |

### query_params

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 90,221 | 0.77 | 0.63 | 0.95 | 3.13 | 0 |
| blacksheep | 74,526 | 0.86 | 0.85 | 0.88 | 0.96 | 0 |
| starlette | 63,832 | 1.01 | 0.98 | 1.03 | 2.18 | 0 |
| litestar | 48,828 | 1.31 | 1.31 | 1.34 | 1.42 | 0 |
| sanic | 42,798 | 1.50 | 1.52 | 1.59 | 2.25 | 0 |
| fastapi | 25,710 | 2.49 | 2.46 | 2.59 | 2.76 | 0 |

### routing_stress

| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |
|---|---:|---:|---:|---:|---:|---:|
| hawkapi | 134,356 | 0.50 | 0.41 | 0.68 | 2.06 | 0 |
| blacksheep | 121,214 | 0.53 | 0.52 | 0.55 | 0.96 | 0 |
| litestar | 56,085 | 1.14 | 1.14 | 1.17 | 1.24 | 0 |
| sanic | 42,801 | 1.52 | 1.47 | 1.68 | 3.66 | 0 |
| starlette | 27,397 | 2.33 | 2.33 | 2.38 | 2.51 | 0 |
| fastapi | 17,123 | 3.75 | 3.70 | 3.78 | 4.93 | 0 |


## How HawkAPI Ranks

HawkAPI placement per scenario:

- body_validation: #1
- json: #1
- path_param: #1
- plaintext: #2
- query_params: #1
- routing_stress: #1
