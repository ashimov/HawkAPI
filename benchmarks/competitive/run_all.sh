#!/usr/bin/env bash
# Run the full competitive benchmark suite and generate the report.
#
# Usage:
#   ./benchmarks/competitive/run_all.sh
#   DURATION=30 CONNECTIONS=128 ./benchmarks/competitive/run_all.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DURATION="${DURATION:-10}"
CONNECTIONS="${CONNECTIONS:-64}"
THREADS="${THREADS:-4}"

cd "$REPO_ROOT"

if ! command -v wrk >/dev/null 2>&1; then
    echo "ERROR: wrk not installed. brew install wrk" >&2
    exit 1
fi

if ! uv run --quiet python -c "import granian" 2>/dev/null; then
    echo "ERROR: granian not available. uv sync --extra granian" >&2
    exit 1
fi

echo "==> Running competitive benchmarks"
echo "    duration:    ${DURATION}s"
echo "    connections: ${CONNECTIONS}"
echo "    threads:     ${THREADS}"
echo

uv run python benchmarks/competitive/runner.py \
    --duration "$DURATION" \
    --connections "$CONNECTIONS" \
    --threads "$THREADS"

echo
echo "==> Generating report"
uv run python benchmarks/competitive/generate_report.py

echo
echo "==> Done. See benchmarks/competitive/RESULTS.md"
