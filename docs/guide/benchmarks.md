# Benchmarks

HawkAPI competes head-to-head with the top Python ASGI frameworks on six
standardised scenarios. Numbers are regenerated automatically every Monday
and on every release — see the live
[`benchmarks/competitive/RESULTS.md`](https://github.com/ashimov/Hawk/blob/main/benchmarks/competitive/RESULTS.md).

## Methodology

- **Scenarios**: `json`, `plaintext`, `path_param`, `body_validation`,
  `query_params`, `routing_stress` — identical endpoint surface in every
  framework's test app so the numbers reflect framework overhead, not the
  workload.
- **Server**: Granian (1 worker, ASGI mode). Same for every framework to
  isolate framework cost from transport.
- **Load tool**: `wrk` — 4 threads × 64 connections × 10 seconds per scenario.
- **Runner**: GitHub Actions `ubuntu-latest` (shared Azure VMs). Numbers are
  relative — same runner class for every framework inside one run. Absolute
  numbers vary between runs; relative ordering is stable.
- **Frameworks tested**: HawkAPI, FastAPI, Litestar, BlackSheep, Starlette,
  Sanic.

## Latest numbers

As of 2026-04-17 (first committed snapshot), HawkAPI leads throughput on
**five of six** scenarios — `body_validation`, `json`, `path_param`,
`query_params`, `routing_stress`. BlackSheep leads `plaintext`; HawkAPI is
within 11 % on that scenario.

See
[`benchmarks/competitive/RESULTS.md`](https://github.com/ashimov/Hawk/blob/main/benchmarks/competitive/RESULTS.md)
for the full throughput + p99 latency breakdown per run.

## Reproducing locally

```bash
# macOS
brew install wrk

# Ubuntu
sudo apt-get install -y wrk

uv sync --extra bench
./benchmarks/competitive/run_all.sh
# Results appear in benchmarks/competitive/RESULTS.md
```

Override duration and concurrency for deeper runs:

```bash
DURATION=30 CONNECTIONS=128 ./benchmarks/competitive/run_all.sh
```

## CI integration

The `Competitive benchmarks` workflow runs:

- **On every release** — `RESULTS.md` is attached as a release asset.
- **Every Monday at 06:00 UTC** — opens a PR with the refresh if the numbers
  changed (so drift is visible in PR form before merging).
- **On `workflow_dispatch`** — optional `duration` and `connections` inputs
  for ad-hoc longer runs.

## Honest caveats

- Benchmarks are point-in-time measurements; real production workloads mix
  scenarios, pay memory pressure, hit databases, and involve middleware the
  bench apps don't.
- wrk on a shared GitHub runner sees run-to-run variance of ±5 – 10 %.
- HawkAPI is optimised for these scenarios deliberately (mypyc-compiled hot
  paths, msgspec encoding, radix-tree routing). That's the point of shipping
  them: "be the fastest choice for the 95 % of your endpoints that are HTTP +
  JSON."
