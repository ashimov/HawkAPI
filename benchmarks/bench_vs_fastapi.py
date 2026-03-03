"""Benchmark: HawkAPI vs FastAPI — side-by-side ASGI-level comparison.

Tests both frameworks on identical workloads at the ASGI protocol level
(no HTTP server overhead — pure framework performance).

Run: python benchmarks/bench_vs_fastapi.py
"""

import asyncio
import json
import time

import msgspec
import pydantic

# ============================================================
# 1. Setup: identical apps in both frameworks
# ============================================================

# --- HawkAPI app ---

from hawkapi import HawkAPI

hawk_app = HawkAPI(openapi_url=None)


class HawkItem(msgspec.Struct):
    name: str
    price: float
    description: str = ""


@hawk_app.get("/ping")
async def hawk_ping():
    return {"pong": True}


@hawk_app.get("/users/{user_id:int}")
async def hawk_get_user(user_id: int):
    return {"id": user_id, "name": "Alice", "email": "alice@example.com"}


@hawk_app.post("/items")
async def hawk_create_item(body: HawkItem):
    return {"id": 1, "name": body.name, "price": body.price}


@hawk_app.get("/large")
async def hawk_large():
    return [
        {"id": i, "name": f"User {i}", "email": f"user{i}@test.com", "active": True}
        for i in range(100)
    ]


# --- FastAPI app ---

from fastapi import FastAPI

fast_app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


class FastItem(pydantic.BaseModel):
    name: str
    price: float
    description: str = ""


@fast_app.get("/ping")
async def fast_ping():
    return {"pong": True}


@fast_app.get("/users/{user_id}")
async def fast_get_user(user_id: int):
    return {"id": user_id, "name": "Alice", "email": "alice@example.com"}


@fast_app.post("/items")
async def fast_create_item(body: FastItem):
    return {"id": 1, "name": body.name, "price": body.price}


@fast_app.get("/large")
async def fast_large():
    return [
        {"id": i, "name": f"User {i}", "email": f"user{i}@test.com", "active": True}
        for i in range(100)
    ]


# ============================================================
# 2. ASGI-level benchmark harness
# ============================================================


def _bench(app, method, path, body, headers=None, iterations=5_000, warmup=200):
    """Benchmark an ASGI app by calling it directly (no HTTP)."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": b"",
        "root_path": "",
        "headers": headers or [],
        "server": ("localhost", 8000),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    sent = []

    async def send(msg):
        sent.append(msg)

    loop = asyncio.new_event_loop()

    # Warmup
    for _ in range(warmup):
        sent.clear()
        loop.run_until_complete(app(scope, receive, send))

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        sent.clear()
        loop.run_until_complete(app(scope, receive, send))
    elapsed = time.perf_counter() - start

    loop.close()

    return elapsed, iterations


def _bench_serialization(iterations=20_000):
    """Benchmark raw serialization: msgspec vs json+pydantic."""
    data = {
        "id": 42,
        "name": "Alice",
        "email": "alice@example.com",
        "active": True,
        "tags": ["admin", "user"],
        "metadata": {"role": "admin", "dept": "eng"},
    }

    # msgspec
    encoder = msgspec.json.Encoder()
    start = time.perf_counter()
    for _ in range(iterations):
        encoder.encode(data)
    msgspec_time = time.perf_counter() - start

    # stdlib json (what FastAPI uses internally via Starlette)
    start = time.perf_counter()
    for _ in range(iterations):
        json.dumps(data).encode("utf-8")
    json_time = time.perf_counter() - start

    return msgspec_time, json_time, iterations


# ============================================================
# 3. Run all benchmarks
# ============================================================


def main():
    print("=" * 70)
    print("HawkAPI vs FastAPI — ASGI-level Benchmark")
    print("=" * 70)
    print(f"  FastAPI {fastapi.__version__}  |  Pydantic {pydantic.__version__}")
    print(f"  msgspec {msgspec.__version__}")
    print()

    body_json = msgspec.json.encode({"name": "Widget", "price": 9.99})
    content_type_header = [(b"content-type", b"application/json")]

    tests = [
        ("Simple JSON (GET /ping)", "GET", "/ping", b"", None),
        ("Path param (GET /users/42)", "GET", "/users/42", b"", None),
        ("Body decode (POST /items)", "POST", "/items", body_json, content_type_header),
        ("Large response (100 items)", "GET", "/large", b"", None),
    ]

    results = []

    for label, method, path, body, headers in tests:
        iters = 3_000 if "large" in label.lower() else 5_000

        hawk_elapsed, _ = _bench(hawk_app, method, path, body, headers, iterations=iters)
        fast_elapsed, _ = _bench(fast_app, method, path, body, headers, iterations=iters)

        hawk_us = (hawk_elapsed / iters) * 1_000_000
        fast_us = (fast_elapsed / iters) * 1_000_000
        hawk_rps = iters / hawk_elapsed
        fast_rps = iters / fast_elapsed
        speedup = fast_elapsed / hawk_elapsed

        results.append((label, hawk_us, fast_us, hawk_rps, fast_rps, speedup))

    # Print request/response results
    print("Request/Response Cycle (ASGI-level, no HTTP server):")
    print("-" * 70)
    print(f"  {'Test':<35} {'HawkAPI':>10} {'FastAPI':>10} {'Speedup':>10}")
    print(f"  {'':35} {'(us/req)':>10} {'(us/req)':>10} {'':>10}")
    print("-" * 70)

    for label, hawk_us, fast_us, hawk_rps, fast_rps, speedup in results:
        print(f"  {label:<35} {hawk_us:>8.1f}us {fast_us:>8.1f}us {speedup:>8.1f}x")

    print()

    # Throughput summary
    print("Throughput (req/sec):")
    print("-" * 70)
    print(f"  {'Test':<35} {'HawkAPI':>10} {'FastAPI':>10}")
    print("-" * 70)
    for label, _, _, hawk_rps, fast_rps, _ in results:
        print(f"  {label:<35} {hawk_rps:>9,.0f} {fast_rps:>9,.0f}")

    print()

    # Serialization benchmark
    print("Serialization (encode dict to JSON bytes):")
    print("-" * 70)
    msgspec_time, json_time, iters = _bench_serialization()
    msgspec_ops = iters / msgspec_time
    json_ops = iters / json_time
    print(f"  msgspec.json.Encoder:  {msgspec_ops:>12,.0f} ops/sec  ({msgspec_time:.3f}s)")
    print(f"  json.dumps + encode:   {json_ops:>12,.0f} ops/sec  ({json_time:.3f}s)")
    print(f"  Speedup:               {json_time / msgspec_time:>11.1f}x")

    print()
    print("=" * 70)

    # Summary
    avg_speedup = sum(r[5] for r in results) / len(results)
    print(f"  Average speedup: {avg_speedup:.1f}x faster than FastAPI")
    print("=" * 70)


import fastapi

if __name__ == "__main__":
    main()
