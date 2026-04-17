"""Competitive benchmark runner.

Spawns each framework app under Granian, runs wrk against identical scenarios,
and saves results as JSON. Use generate_report.py to produce RESULTS.md.

Usage:
    python benchmarks/competitive/runner.py                  # all frameworks, all scenarios
    python benchmarks/competitive/runner.py --framework hawkapi
    python benchmarks/competitive/runner.py --scenario json
    python benchmarks/competitive/runner.py --duration 10 --connections 64
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
APPS_DIR = ROOT / "apps"

FRAMEWORKS: dict[str, tuple[str, list[str]]] = {
    "hawkapi": (
        "benchmarks.competitive.apps.hawkapi_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
    "fastapi": (
        "benchmarks.competitive.apps.fastapi_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
    "litestar": (
        "benchmarks.competitive.apps.litestar_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
    "blacksheep": (
        "benchmarks.competitive.apps.blacksheep_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
    "starlette": (
        "benchmarks.competitive.apps.starlette_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
    "sanic": (
        "benchmarks.competitive.apps.sanic_app:app",
        ["granian", "--interface", "asgi", "--workers", "1", "--no-ws"],
    ),
}


@dataclass
class Scenario:
    name: str
    method: str
    path: str
    body: str | None = None
    headers: dict[str, str] | None = None


SCENARIOS: list[Scenario] = [
    Scenario("json", "GET", "/json"),
    Scenario("plaintext", "GET", "/plaintext"),
    Scenario("path_param", "GET", "/users/42"),
    Scenario(
        "body_validation",
        "POST",
        "/items",
        body='{"name":"widget","price":9.99,"description":"x"}',
        headers={"Content-Type": "application/json"},
    ),
    Scenario("query_params", "GET", "/search?q=hello&limit=20"),
    Scenario("routing_stress", "GET", "/route/87"),
]


@dataclass
class BenchResult:
    framework: str
    scenario: str
    requests_per_sec: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_avg_ms: float
    transfer_per_sec: str
    errors: int
    duration_sec: float
    timestamp: str


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _spawn_server(framework: str, port: int) -> subprocess.Popen[bytes]:
    module_path, base_cmd = FRAMEWORKS[framework]
    cmd = [
        *base_cmd,
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        module_path,
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(  # noqa: S603
        cmd,
        cwd=str(ROOT.parent.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


_LATENCY_RE = re.compile(
    r"Latency\s+([\d.]+)(\w+)\s+([\d.]+)(\w+)\s+([\d.]+)(\w+)\s+([\d.]+)%"
)
_REQ_RE = re.compile(r"Requests/sec:\s+([\d.]+)")
_TRANSFER_RE = re.compile(r"Transfer/sec:\s+([\d.]+\w+)")
_LATENCY_DIST_RE = re.compile(r"\s+(\d+)%\s+([\d.]+)(\w+)")
_ERRORS_RE = re.compile(r"Non-2xx or 3xx responses:\s+(\d+)")


def _to_ms(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "us":
        return value / 1000.0
    if unit == "ms":
        return value
    if unit == "s":
        return value * 1000.0
    if unit == "m":
        return value * 60_000.0
    return value


def _parse_wrk(output: str) -> tuple[float, float, float, float, float, str, int]:
    """Parse wrk output. Returns (rps, avg_ms, p50_ms, p95_ms, p99_ms, transfer, errors)."""
    rps = 0.0
    avg_ms = 0.0
    transfer = "0"
    errors = 0
    p50_ms = p95_ms = p99_ms = 0.0

    for line in output.splitlines():
        if m := _REQ_RE.search(line):
            rps = float(m.group(1))
        elif m := _TRANSFER_RE.search(line):
            transfer = m.group(1)
        elif m := _ERRORS_RE.search(line):
            errors = int(m.group(1))
        elif m := _LATENCY_RE.search(line):
            avg_ms = _to_ms(float(m.group(1)), m.group(2))
        elif m := _LATENCY_DIST_RE.search(line):
            pct = int(m.group(1))
            ms = _to_ms(float(m.group(2)), m.group(3))
            if pct == 50:
                p50_ms = ms
            elif pct in (90, 95):
                p95_ms = ms
            elif pct == 99:
                p99_ms = ms

    return rps, avg_ms, p50_ms, p95_ms, p99_ms, transfer, errors


def _wrk_lua_script(scenario: Scenario) -> str:
    """Build a Lua script for non-GET wrk runs."""
    if scenario.method == "GET":
        return ""
    headers = "\n".join(
        f'wrk.headers["{k}"] = "{v}"' for k, v in (scenario.headers or {}).items()
    )
    body = (scenario.body or "").replace('"', '\\"')
    return f"""
wrk.method = "{scenario.method}"
{headers}
wrk.body = "{body}"
"""


def _run_wrk(
    port: int,
    scenario: Scenario,
    duration: int,
    connections: int,
    threads: int,
) -> str:
    url = f"http://127.0.0.1:{port}{scenario.path}"
    cmd = [
        "wrk",
        "-t",
        str(threads),
        "-c",
        str(connections),
        "-d",
        f"{duration}s",
        "--latency",
    ]
    script_path: Path | None = None
    if scenario.method != "GET":
        script_path = RESULTS_DIR / f".tmp_{scenario.name}.lua"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text(_wrk_lua_script(scenario))
        cmd += ["-s", str(script_path)]
    cmd.append(url)

    proc = subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, timeout=duration + 30
    )
    if script_path and script_path.exists():
        script_path.unlink()
    if proc.returncode != 0:
        raise RuntimeError(f"wrk failed: {proc.stderr}")
    return proc.stdout


def _warmup(port: int, scenario: Scenario) -> None:
    """Send a few requests to warm up caches."""
    url = f"http://127.0.0.1:{port}{scenario.path}"
    for _ in range(20):
        try:
            subprocess.run(  # noqa: S603, S607
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-X",
                    scenario.method,
                    "-d",
                    scenario.body or "",
                    "-H",
                    "Content-Type: application/json",
                    url,
                ],
                timeout=2,
                check=False,
            )
        except Exception:
            pass


def run_one(
    framework: str,
    scenario: Scenario,
    duration: int,
    connections: int,
    threads: int,
) -> BenchResult | None:
    port = _free_port()
    proc = _spawn_server(framework, port)
    try:
        if not _wait_ready(port, timeout=15):
            print(f"  [{framework}] failed to start", file=sys.stderr)
            return None
        _warmup(port, scenario)
        output = _run_wrk(port, scenario, duration, connections, threads)
        rps, avg, p50, p95, p99, transfer, errors = _parse_wrk(output)
        return BenchResult(
            framework=framework,
            scenario=scenario.name,
            requests_per_sec=rps,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            latency_avg_ms=avg,
            transfer_per_sec=transfer,
            errors=errors,
            duration_sec=float(duration),
            timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Competitive framework benchmark")
    parser.add_argument("--framework", choices=list(FRAMEWORKS), help="Run one framework only")
    parser.add_argument(
        "--scenario", choices=[s.name for s in SCENARIOS], help="Run one scenario only"
    )
    parser.add_argument("--duration", type=int, default=10, help="seconds per run")
    parser.add_argument("--connections", type=int, default=64, help="concurrent connections")
    parser.add_argument("--threads", type=int, default=4, help="wrk threads")
    args = parser.parse_args()

    if shutil.which("wrk") is None:
        print("ERROR: wrk not installed. brew install wrk", file=sys.stderr)
        return 1
    if shutil.which("granian") is None:
        print("ERROR: granian not installed. uv sync --extra granian", file=sys.stderr)
        return 1

    frameworks = [args.framework] if args.framework else list(FRAMEWORKS)
    scenarios = [s for s in SCENARIOS if (args.scenario is None or s.name == args.scenario)]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results: list[BenchResult] = []

    for fw in frameworks:
        for scn in scenarios:
            print(f"  [{fw}] {scn.name} ... ", end="", flush=True)
            result = run_one(fw, scn, args.duration, args.connections, args.threads)
            if result is None:
                print("SKIP")
                continue
            print(f"{result.requests_per_sec:>10,.0f} RPS  p99={result.latency_p99_ms:.2f}ms")
            out = RESULTS_DIR / f"{fw}_{scn.name}.json"
            out.write_text(json.dumps(asdict(result), indent=2))
            all_results.append(result)

    summary = RESULTS_DIR / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
                "duration_sec": args.duration,
                "connections": args.connections,
                "threads": args.threads,
                "results": [asdict(r) for r in all_results],
            },
            indent=2,
        )
    )
    print(f"\nWrote {len(all_results)} results to {RESULTS_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
