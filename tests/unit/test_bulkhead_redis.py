"""Tests for the Redis-backed bulkhead backend.

Uses fakeredis so the suite runs without a live Redis instance.
"""

from __future__ import annotations

import asyncio

import pytest

redis_pkg = pytest.importorskip("redis")
fakeredis = pytest.importorskip("fakeredis")

from hawkapi.middleware.bulkhead import BulkheadFullError  # noqa: E402
from hawkapi.middleware.bulkhead_redis import RedisBulkheadBackend  # noqa: E402


@pytest.fixture
async def redis_client():
    """Yield a fresh fakeredis.aioredis.FakeRedis per test."""
    client = fakeredis.aioredis.FakeRedis()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


async def test_redis_backend_acquire_release_round_trip(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    token = await backend.acquire("x", limit=2, max_wait=0.0)
    assert isinstance(token, str)
    await backend.release("x", token)


async def test_redis_backend_fail_fast_when_full(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    await backend.acquire("x", limit=2, max_wait=0.0)
    await backend.acquire("x", limit=2, max_wait=0.0)
    with pytest.raises(BulkheadFullError):
        await backend.acquire("x", limit=2, max_wait=0.0)


async def test_redis_backend_queue_then_release(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client)
    t1 = await backend.acquire("x", limit=1, max_wait=0.0)

    async def release_after(delay: float) -> None:
        await asyncio.sleep(delay)
        await backend.release("x", t1)

    releaser = asyncio.create_task(release_after(0.05))
    try:
        t2 = await backend.acquire("x", limit=1, max_wait=0.5)
        await backend.release("x", t2)
    finally:
        await releaser


async def test_redis_backend_two_clients_share_capacity(redis_client) -> None:
    b1 = RedisBulkheadBackend(redis_client)
    b2 = RedisBulkheadBackend(redis_client)
    await b1.acquire("x", limit=1, max_wait=0.0)
    with pytest.raises(BulkheadFullError):
        await b2.acquire("x", limit=1, max_wait=0.0)


async def test_redis_backend_lease_ttl_reclaims_after_crash(redis_client) -> None:
    backend = RedisBulkheadBackend(redis_client, lease_ttl=0.05)
    await backend.acquire("x", limit=1, max_wait=0.0)
    await asyncio.sleep(0.1)
    reaped = await backend.reap_expired_leases("x")
    assert reaped == 1
    token = await backend.acquire("x", limit=1, max_wait=0.0)
    assert token is not None
    await backend.release("x", token)
