"""Benchmark: streaming and SSE response throughput (ASGI-level).

Invokes StreamingResponse and EventSourceResponse directly via their
``__call__`` ASGI interface — the same pattern used by the unit tests.
"""

from __future__ import annotations

import asyncio
import time

from hawkapi import HawkAPI
from hawkapi.responses.sse import EventSourceResponse, ServerSentEvent
from hawkapi.responses.streaming import StreamingResponse

CHUNK_SIZE = 1024  # 1 KB
NUM_CHUNKS = 100
NUM_EVENTS = 100


def _make_scope(path: str = "/") -> dict:
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


def bench_streaming_throughput():
    """Benchmark StreamingResponse: 100 chunks of 1 KB each."""
    print("=== Streaming Response Benchmark ===\n")

    chunk = b"x" * CHUNK_SIZE
    scope = _make_scope()
    iterations = 1_000
    loop = asyncio.new_event_loop()

    async def run_once():
        async def generate():
            for _ in range(NUM_CHUNKS):
                yield chunk

        resp = StreamingResponse(generate(), content_type="application/octet-stream")
        collected: list[dict] = []

        async def send(msg):
            collected.append(msg)

        await resp(scope, _receive, send)
        return collected

    # Warmup
    for _ in range(10):
        loop.run_until_complete(run_once())

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        loop.run_until_complete(run_once())
    elapsed = time.perf_counter() - start

    loop.close()

    per_req_us = (elapsed / iterations) * 1_000_000
    throughput_mb = (iterations * NUM_CHUNKS * CHUNK_SIZE) / elapsed / (1024 * 1024)

    print(f"Streaming {NUM_CHUNKS} x {CHUNK_SIZE} B chunks:")
    print(f"  {iterations:,} iterations in {elapsed:.3f}s")
    print(f"  {per_req_us:.1f} us/req  |  {throughput_mb:.1f} MB/s")
    print()


def bench_sse_throughput():
    """Benchmark EventSourceResponse: 100 SSE events."""
    print("=== SSE Response Benchmark ===\n")

    scope = _make_scope()
    iterations = 1_000
    loop = asyncio.new_event_loop()

    async def run_once():
        async def generate():
            for i in range(NUM_EVENTS):
                yield ServerSentEvent(data=f"message {i}", event="update", id=str(i))

        resp = EventSourceResponse(generate())
        collected: list[dict] = []

        async def send(msg):
            collected.append(msg)

        await resp(scope, _receive, send)
        return collected

    # Warmup
    for _ in range(10):
        loop.run_until_complete(run_once())

    # Benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        loop.run_until_complete(run_once())
    elapsed = time.perf_counter() - start

    loop.close()

    per_req_us = (elapsed / iterations) * 1_000_000
    events_per_sec = (iterations * NUM_EVENTS) / elapsed

    print(f"SSE {NUM_EVENTS} events per response:")
    print(f"  {iterations:,} iterations in {elapsed:.3f}s")
    print(f"  {per_req_us:.1f} us/req  |  {events_per_sec:,.0f} events/s")
    print()


def bench_buffered_vs_streaming():
    """Compare latency: buffered JSON response vs streaming response."""
    print("=== Buffered vs Streaming Latency ===\n")

    total_data = b"x" * (NUM_CHUNKS * CHUNK_SIZE)

    # Buffered: use a route that returns a dict (JSON-encoded)
    app_buffered = HawkAPI(openapi_url=None)

    @app_buffered.get("/buffered")
    async def buffered():
        return {"data": total_data.decode("ascii")}

    buffered_scope = {
        "type": "http",
        "method": "GET",
        "path": "/buffered",
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }

    # Streaming: invoke StreamingResponse directly at ASGI level
    chunk = b"x" * CHUNK_SIZE
    stream_scope = _make_scope()

    iterations = 1_000
    loop = asyncio.new_event_loop()

    # --- Buffered ---
    async def run_buffered():
        async def send(msg):
            pass

        await app_buffered(buffered_scope, _receive, send)

    for _ in range(10):
        loop.run_until_complete(run_buffered())

    start = time.perf_counter()
    for _ in range(iterations):
        loop.run_until_complete(run_buffered())
    buffered_time = time.perf_counter() - start

    # --- Streaming ---
    async def run_streaming():
        async def generate():
            for _ in range(NUM_CHUNKS):
                yield chunk

        resp = StreamingResponse(generate(), content_type="application/octet-stream")

        async def send(msg):
            pass

        await resp(stream_scope, _receive, send)

    for _ in range(10):
        loop.run_until_complete(run_streaming())

    start = time.perf_counter()
    for _ in range(iterations):
        loop.run_until_complete(run_streaming())
    streaming_time = time.perf_counter() - start

    loop.close()

    buf_us = (buffered_time / iterations) * 1_000_000
    str_us = (streaming_time / iterations) * 1_000_000

    print(f"Payload: {NUM_CHUNKS * CHUNK_SIZE / 1024:.0f} KB, {iterations:,} iterations")
    print(f"  Buffered JSON:     {buf_us:.1f} us/req")
    print(f"  Streaming chunks:  {str_us:.1f} us/req")
    if buf_us > 0 and str_us > 0:
        ratio = buf_us / str_us
        faster = "Streaming" if ratio > 1 else "Buffered"
        print(f"  {faster} is {max(ratio, 1 / ratio):.1f}x faster")
    print()


if __name__ == "__main__":
    bench_streaming_throughput()
    bench_sse_throughput()
    bench_buffered_vs_streaming()
