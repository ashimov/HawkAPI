"""Generate RESULTS.md from benchmarks/competitive/results/summary.json.

Usage: python benchmarks/competitive/generate_report.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS_DIR = ROOT / "results"
SUMMARY = RESULTS_DIR / "summary.json"
OUT = ROOT / "RESULTS.md"


def fmt_rps(rps: float) -> str:
    return f"{rps:>10,.0f}"


def fmt_ms(ms: float) -> str:
    return f"{ms:.2f}"


def main() -> int:
    if not SUMMARY.exists():
        print(f"ERROR: {SUMMARY} not found. Run runner.py first.", file=sys.stderr)
        return 1

    data = json.loads(SUMMARY.read_text())
    results = data["results"]
    if not results:
        print("ERROR: no results", file=sys.stderr)
        return 1

    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_scenario[r["scenario"]].append(r)

    lines: list[str] = []
    lines.append("# Competitive Benchmark Results\n")
    lines.append(f"**Generated:** {data['timestamp']}  ")
    lines.append(
        f"**Config:** {data['duration_sec']}s × "
        f"{data['connections']} connections × "
        f"{data['threads']} wrk threads  "
    )
    lines.append("**Server:** Granian (1 worker, ASGI)  ")
    lines.append("**Tool:** wrk\n")

    lines.append("## Summary — Throughput (Requests/sec, higher is better)\n")
    frameworks = sorted({r["framework"] for r in results})
    scenarios = sorted(by_scenario.keys())

    header = "| Scenario | " + " | ".join(frameworks) + " |"
    sep = "|" + "---|" * (len(frameworks) + 1)
    lines.append(header)
    lines.append(sep)

    for scn in scenarios:
        scn_results = {r["framework"]: r for r in by_scenario[scn]}
        max_rps = max((r["requests_per_sec"] for r in by_scenario[scn]), default=0.0)
        row = [scn]
        for fw in frameworks:
            r = scn_results.get(fw)
            if r is None:
                row.append("—")
            else:
                rps = r["requests_per_sec"]
                star = " 🏆" if rps == max_rps and rps > 0 else ""
                row.append(f"{fmt_rps(rps).strip()}{star}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("\n## p99 Latency (ms, lower is better)\n")
    lines.append(header)
    lines.append(sep)
    for scn in scenarios:
        scn_results = {r["framework"]: r for r in by_scenario[scn]}
        valid = [r["latency_p99_ms"] for r in by_scenario[scn] if r["latency_p99_ms"] > 0]
        min_p99 = min(valid) if valid else 0.0
        row = [scn]
        for fw in frameworks:
            r = scn_results.get(fw)
            if r is None or r["latency_p99_ms"] == 0:
                row.append("—")
            else:
                p99 = r["latency_p99_ms"]
                star = " 🏆" if p99 == min_p99 else ""
                row.append(f"{fmt_ms(p99)}{star}")
        lines.append("| " + " | ".join(row) + " |")

    lines.append("\n## Detailed Results\n")
    for scn in scenarios:
        lines.append(f"### {scn}\n")
        lines.append("| Framework | RPS | avg ms | p50 ms | p95 ms | p99 ms | errors |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for r in sorted(by_scenario[scn], key=lambda x: x["requests_per_sec"], reverse=True):
            lines.append(
                f"| {r['framework']} "
                f"| {fmt_rps(r['requests_per_sec']).strip()} "
                f"| {fmt_ms(r['latency_avg_ms'])} "
                f"| {fmt_ms(r['latency_p50_ms'])} "
                f"| {fmt_ms(r['latency_p95_ms'])} "
                f"| {fmt_ms(r['latency_p99_ms'])} "
                f"| {r['errors']} |"
            )
        lines.append("")

    lines.append("\n## How HawkAPI Ranks\n")
    rankings: dict[str, list[str]] = defaultdict(list)
    for scn in scenarios:
        ranked = sorted(by_scenario[scn], key=lambda x: x["requests_per_sec"], reverse=True)
        for idx, r in enumerate(ranked, start=1):
            rankings[r["framework"]].append(f"{scn}: #{idx}")

    if "hawkapi" in rankings:
        lines.append("HawkAPI placement per scenario:\n")
        for entry in rankings["hawkapi"]:
            lines.append(f"- {entry}")
        lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
