"""Benchmark: cold start import time for HawkAPI."""

from __future__ import annotations

import subprocess
import sys
import time


def bench_import_time(module: str, runs: int = 5) -> float:
    """Measure import time of a module in a fresh subprocess."""
    times: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - start
        if result.returncode != 0:
            print(f"ERROR importing {module}: {result.stderr}")
            continue
        times.append(elapsed)
    return sum(times) / len(times) if times else 0.0


def main() -> None:
    modules = [
        "hawkapi",
        "hawkapi.app",
        "hawkapi.routing.router",
    ]

    print("HawkAPI Cold Start Benchmark")
    print("=" * 40)
    for mod in modules:
        avg = bench_import_time(mod)
        print(f"  {mod:<30s} {avg*1000:.1f}ms")
    print()

    # Compare with serverless-relevant: just the core
    print("Comparison:")
    for mod in ["json", "msgspec"]:
        avg = bench_import_time(mod)
        print(f"  {mod:<30s} {avg*1000:.1f}ms")


if __name__ == "__main__":
    main()
