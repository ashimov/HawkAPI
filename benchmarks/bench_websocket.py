"""Benchmark: WebSocket message echo latency and JSON throughput (ASGI-level)."""

from __future__ import annotations

import asyncio
import time

import msgspec

from hawkapi import HawkAPI
from hawkapi.websocket.connection import WebSocket, WebSocketDisconnect

NUM_MESSAGES = 1_000


def _make_ws_scope(path: str = "/ws") -> dict:
    return {
        "type": "websocket",
        "path": path,
        "headers": [],
        "query_string": b"",
    }


def bench_echo_latency():
    """Benchmark WebSocket text echo: send a message and receive it back."""
    print("=== WebSocket Echo Latency Benchmark ===\n")

    app = HawkAPI(openapi_url=None)

    @app.websocket("/ws")
    async def ws_echo(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                text = await ws.receive_text()
                await ws.send_text(text)
        except (WebSocketDisconnect, StopIteration):
            pass

    iterations = NUM_MESSAGES
    loop = asyncio.new_event_loop()

    async def run_echo():
        """Simulate a full WebSocket echo session at the ASGI level."""
        scope = _make_ws_scope("/ws")
        messages_to_send = [
            {"type": "websocket.connect"},
        ]
        for i in range(iterations):
            messages_to_send.append({"type": "websocket.receive", "text": f"msg-{i}"})
        messages_to_send.append({"type": "websocket.disconnect", "code": 1000})

        msg_iter = iter(messages_to_send)
        sent: list[dict] = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        await app(scope, receive, send)
        return sent

    # Warmup
    loop.run_until_complete(run_echo())

    # Benchmark
    start = time.perf_counter()
    sent = loop.run_until_complete(run_echo())
    elapsed = time.perf_counter() - start

    loop.close()

    # sent includes: websocket.accept + N x websocket.send
    echo_count = sum(1 for m in sent if m.get("type") == "websocket.send")
    per_msg_us = (elapsed / echo_count) * 1_000_000 if echo_count else 0
    msgs_per_sec = echo_count / elapsed if elapsed > 0 else 0

    print(f"Echo {echo_count:,} text messages:")
    print(f"  Total time:    {elapsed:.3f}s")
    print(f"  Per message:   {per_msg_us:.1f} us")
    print(f"  Messages/sec:  {msgs_per_sec:,.0f}")
    print()


def bench_json_throughput():
    """Benchmark WebSocket JSON send/receive throughput."""
    print("=== WebSocket JSON Throughput Benchmark ===\n")

    app = HawkAPI(openapi_url=None)

    @app.websocket("/ws-json")
    async def ws_json(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                data = await ws.receive_json()
                await ws.send_json(data)
        except (WebSocketDisconnect, StopIteration):
            pass

    iterations = NUM_MESSAGES
    payload = {"id": 42, "name": "benchmark", "values": [1, 2, 3, 4, 5]}
    payload_text = msgspec.json.encode(payload).decode("utf-8")

    loop = asyncio.new_event_loop()

    async def run_json():
        scope = _make_ws_scope("/ws-json")
        messages_to_send = [
            {"type": "websocket.connect"},
        ]
        for _ in range(iterations):
            messages_to_send.append({"type": "websocket.receive", "text": payload_text})
        messages_to_send.append({"type": "websocket.disconnect", "code": 1000})

        msg_iter = iter(messages_to_send)
        sent: list[dict] = []

        async def receive():
            return next(msg_iter)

        async def send(msg):
            sent.append(msg)

        await app(scope, receive, send)
        return sent

    # Warmup
    loop.run_until_complete(run_json())

    # Benchmark
    start = time.perf_counter()
    sent = loop.run_until_complete(run_json())
    elapsed = time.perf_counter() - start

    loop.close()

    json_count = sum(1 for m in sent if m.get("type") == "websocket.send")
    per_msg_us = (elapsed / json_count) * 1_000_000 if json_count else 0
    msgs_per_sec = json_count / elapsed if elapsed > 0 else 0

    print(f"JSON round-trip {json_count:,} messages ({len(payload_text)} bytes each):")
    print(f"  Total time:    {elapsed:.3f}s")
    print(f"  Per message:   {per_msg_us:.1f} us")
    print(f"  Messages/sec:  {msgs_per_sec:,.0f}")
    print()


if __name__ == "__main__":
    bench_echo_latency()
    bench_json_throughput()
