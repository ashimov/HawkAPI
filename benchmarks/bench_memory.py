"""Benchmark: memory usage for app initialization and request handling."""

from __future__ import annotations

import asyncio
import tracemalloc

from hawkapi import HawkAPI


def _make_scope(path: str = "/ping") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


def _format_bytes(n: int) -> str:
    """Format byte count to a human-readable string."""
    if abs(n) < 1024:
        return f"{n} B"
    elif abs(n) < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    else:
        return f"{n / (1024 * 1024):.2f} MB"


def bench_app_init_memory():
    """Measure memory used to initialize a HawkAPI application."""
    print("=== App Initialization Memory ===\n")

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    app = HawkAPI(title="MemBench")

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    @app.get("/users/{user_id:int}")
    async def get_user(user_id: int):
        return {"id": user_id, "name": "Alice"}

    @app.post("/items")
    async def create_item():
        return {"created": True}

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff = sum(s.size_diff for s in stats)

    print(f"  App + 3 routes:   {_format_bytes(total_diff)}")

    # Also measure peak
    tracemalloc.start()

    app2 = HawkAPI(title="MemBench2")
    for i in range(50):

        @app2.get(f"/route-{i}")
        async def handler():
            return {"ok": True}

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    print(f"  App + 50 routes:  {_format_bytes(peak)}")
    print()


def bench_request_memory():
    """Measure memory usage over 1000 requests."""
    print("=== Memory per 1000 Requests ===\n")

    app = HawkAPI(openapi_url=None)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    loop = asyncio.new_event_loop()
    scope = _make_scope("/ping")

    # Warmup — let caches, singletons, etc. settle
    async def warmup():
        for _ in range(50):

            async def send(msg):
                pass

            await app(scope, _receive, send)

    loop.run_until_complete(warmup())

    # Measure 1000 requests
    request_count = 1000
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    async def run_requests():
        for _ in range(request_count):

            async def send(msg):
                pass

            await app(scope, _receive, send)

    loop.run_until_complete(run_requests())

    snapshot_after = tracemalloc.take_snapshot()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff = sum(s.size_diff for s in stats)
    per_request = total_diff / request_count if request_count else 0

    print(f"  Total for {request_count:,} requests:  {_format_bytes(total_diff)}")
    print(f"  Per request:                {_format_bytes(int(per_request))}")
    print(f"  Peak tracked memory:        {_format_bytes(peak)}")
    print()

    # Top allocations
    top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
    positive = [s for s in top_stats if s.size_diff > 0]
    positive.sort(key=lambda s: s.size_diff, reverse=True)
    if positive:
        print("  Top allocations:")
        for stat in positive[:5]:
            print(f"    {stat}")
    print()

    loop.close()


if __name__ == "__main__":
    bench_app_init_memory()
    bench_request_memory()
