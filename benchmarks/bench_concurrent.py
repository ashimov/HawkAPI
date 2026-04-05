"""Benchmark: concurrent request handling with p50/p95/p99 latencies."""

from __future__ import annotations

import asyncio
import statistics
import time

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


def _percentile(sorted_data: list[float], p: float) -> float:
    """Return the p-th percentile from a sorted list."""
    if not sorted_data:
        return 0.0
    k = (len(sorted_data) - 1) * (p / 100)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


async def _bench_concurrent(app: HawkAPI, concurrency: int, total_requests: int) -> list[float]:
    """Fire *total_requests* through *app* with the given concurrency level.

    Returns a list of per-request latencies (seconds).
    """
    scope = _make_scope("/ping")
    latencies: list[float] = []
    sem = asyncio.Semaphore(concurrency)

    async def single_request():
        async with sem:

            async def send(msg):
                pass

            start = time.perf_counter()
            await app(scope, _receive, send)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

    tasks = [asyncio.create_task(single_request()) for _ in range(total_requests)]
    await asyncio.gather(*tasks)
    return latencies


def bench_concurrent():
    """Benchmark concurrent request handling at various concurrency levels."""
    print("=== Concurrent Request Benchmark ===\n")

    app = HawkAPI(openapi_url=None)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    # Warmup with sequential requests
    loop = asyncio.new_event_loop()

    async def warmup():
        scope = _make_scope("/ping")
        for _ in range(100):

            async def send(msg):
                pass

            await app(scope, _receive, send)

    loop.run_until_complete(warmup())

    concurrency_levels = [10, 50, 100]
    total_per_level = 1_000

    for level in concurrency_levels:
        latencies = loop.run_until_complete(_bench_concurrent(app, level, total_per_level))
        latencies.sort()

        p50 = _percentile(latencies, 50) * 1_000_000  # us
        p95 = _percentile(latencies, 95) * 1_000_000
        p99 = _percentile(latencies, 99) * 1_000_000
        mean = statistics.mean(latencies) * 1_000_000

        print(f"Concurrency={level}, {total_per_level:,} requests:")
        print(f"  Mean:  {mean:.1f} us")
        print(f"  p50:   {p50:.1f} us")
        print(f"  p95:   {p95:.1f} us")
        print(f"  p99:   {p99:.1f} us")
        print()

    loop.close()


if __name__ == "__main__":
    bench_concurrent()
