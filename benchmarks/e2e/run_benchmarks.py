"""End-to-end HTTP benchmark runner (ASGI-level, no network overhead).

Compares HawkAPI vs FastAPI across multiple scenarios using direct ASGI calls.
No external tools (wrk, bombardier) required.

Usage:
    python benchmarks/e2e/run_benchmarks.py
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import msgspec


def _make_scope(method: str, path: str, body: bytes = b"") -> dict[str, Any]:
    headers: list[tuple[bytes, bytes]] = []
    if body:
        headers.append((b"content-type", b"application/json"))
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers,
        "root_path": "",
    }


async def _bench_asgi(app: Any, scope: dict[str, Any], body: bytes, n: int) -> float:
    """Run n requests through the ASGI app and return elapsed seconds."""

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    sent: list[Any] = []

    async def send(msg: Any) -> None:
        sent.append(msg)

    # Warmup
    for _ in range(min(n, 500)):
        sent.clear()
        await app(scope, receive, send)

    # Benchmark
    start = time.perf_counter()
    for _ in range(n):
        sent.clear()
        await app(scope, receive, send)
    return time.perf_counter() - start


def main() -> None:
    iterations = 10_000

    scenarios: list[dict[str, Any]] = [
        {"name": "JSON hello", "method": "GET", "path": "/json", "body": b""},
        {"name": "Path params", "method": "GET", "path": "/users/42", "body": b""},
        {
            "name": "POST body",
            "method": "POST",
            "path": "/items",
            "body": msgspec.json.encode({"id": 1, "name": "Widget", "price": 9.99}),
        },
        {
            "name": "Large response (1000 items)",
            "method": "GET",
            "path": "/items",
            "body": b"",
        },
    ]

    # Load apps — add benchmark dir to path for direct imports
    import importlib
    import sys
    from pathlib import Path

    bench_dir = str(Path(__file__).parent)
    sys.path.insert(0, bench_dir)

    hawk_mod = importlib.import_module("hawkapi_app")
    frameworks: list[tuple[str, Any]] = [("HawkAPI", hawk_mod.app)]

    try:
        fast_mod = importlib.import_module("fastapi_app")
        frameworks.append(("FastAPI", fast_mod.app))
    except ImportError:
        print("FastAPI not installed — skipping FastAPI benchmarks.\n")

    sys.path.pop(0)

    loop = asyncio.new_event_loop()

    print("=" * 70)
    print(f"End-to-End ASGI Benchmark ({iterations:,} iterations per scenario)")
    print("=" * 70)

    results: dict[str, dict[str, float]] = {}

    for fw_name, app in frameworks:
        results[fw_name] = {}
        print(f"\n--- {fw_name} ---")
        for scenario in scenarios:
            scope = _make_scope(scenario["method"], scenario["path"], scenario["body"])
            elapsed = loop.run_until_complete(
                _bench_asgi(app, scope, scenario["body"], iterations)
            )
            per_req_us = (elapsed / iterations) * 1_000_000
            rps = iterations / elapsed
            results[fw_name][scenario["name"]] = per_req_us
            print(f"  {scenario['name']:30s}  {per_req_us:7.1f} µs/req  {rps:>10,.0f} req/sec")

    loop.close()

    # Comparison table
    if len(frameworks) > 1:
        print("\n" + "=" * 70)
        print("Comparison (HawkAPI vs FastAPI)")
        print("=" * 70)
        hawk = results["HawkAPI"]
        fast = results.get("FastAPI", {})
        for name in hawk:
            if name in fast:
                ratio = fast[name] / hawk[name]
                print(f"  {name:30s}  {ratio:.1f}x faster")


if __name__ == "__main__":
    main()
