"""Benchmark: full request → response cycle (ASGI-level)."""

import asyncio
import time

import msgspec

from hawkapi import HawkAPI


class Item(msgspec.Struct):
    name: str
    price: float


def bench_request_response():
    print("=== Request/Response Cycle Benchmark ===\n")

    # --- Minimal JSON response ---
    app_simple = HawkAPI(openapi_url=None)

    @app_simple.get("/ping")
    async def ping():
        return {"pong": True}

    _bench_endpoint(app_simple, "GET", "/ping", b"", "Simple JSON response")

    # --- Path parameter + response ---
    app_param = HawkAPI(openapi_url=None)

    @app_param.get("/users/{user_id:int}")
    async def get_user(user_id: int):
        return {"id": user_id, "name": "Alice"}

    _bench_endpoint(app_param, "GET", "/users/42", b"", "Path param + JSON response")

    # --- POST with body parsing ---
    app_body = HawkAPI(openapi_url=None)

    @app_body.post("/items")
    async def create_item(body: Item):
        return {"name": body.name, "price": body.price}

    body = msgspec.json.encode({"name": "Widget", "price": 9.99})
    _bench_endpoint(
        app_body, "POST", "/items", body, "POST + body decode + JSON response",
        extra_headers=[(b"content-type", b"application/json")],
    )


def _bench_endpoint(app, method, path, body, label, extra_headers=None):
    iterations = 10_000

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": extra_headers or [],
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    sent = []

    async def send(msg):
        sent.append(msg)

    loop = asyncio.new_event_loop()

    # Warmup
    for _ in range(100):
        sent.clear()
        loop.run_until_complete(app(scope, receive, send))

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        sent.clear()
        loop.run_until_complete(app(scope, receive, send))
    elapsed = time.perf_counter() - start

    loop.close()

    per_req_us = (elapsed / iterations) * 1_000_000
    rps = iterations / elapsed

    print(f"{label}:")
    print(f"  {iterations:,} iterations in {elapsed:.3f}s")
    print(f"  {per_req_us:.1f} µs/req  |  {rps:,.0f} req/sec")
    print()


if __name__ == "__main__":
    bench_request_response()
