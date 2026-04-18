"""Redis-backed bulkhead backend — distributed capacity control.

Implementation: one Redis hash per bulkhead name. Each acquired slot is one
field in the hash; field name is a random lease ID, field value is the
acquisition timestamp (seconds, float). ``HLEN`` gives the current occupancy.
``HDEL`` releases. A reaper deletes fields whose timestamp is older than
``lease_ttl``.

This is a "sloppy distributed semaphore": if a worker crashes mid-hold, its
lease survives until the reaper runs, allowing a bounded over-capacity window
up to ``lease_ttl``. Redlock-level correctness is explicitly not a goal.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

from hawkapi.middleware.bulkhead import BulkheadFullError

if TYPE_CHECKING:
    import redis.asyncio as aioredis


class RedisBulkheadBackend:
    """Distributed bulkhead backend using a Redis hash + lease fields."""

    def __init__(
        self,
        client: aioredis.Redis,
        *,
        key_prefix: str = "hawkapi:bulkhead",
        lease_ttl: float = 30.0,
        poll_interval: float = 0.01,
    ) -> None:
        if lease_ttl <= 0:
            raise ValueError("lease_ttl must be > 0")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be > 0")
        self._client = client
        self._key_prefix = key_prefix
        self._lease_ttl = lease_ttl
        self._poll_interval = poll_interval

    def _key(self, name: str) -> str:
        return f"{self._key_prefix}:{name}"

    async def _try_acquire_once(self, name: str, limit: int) -> str | None:
        """Single acquire attempt. Return lease_id on success, None on full."""
        lease_id = uuid.uuid4().hex
        key = self._key(name)
        now_s = time.time()
        pipe = self._client.pipeline()
        pipe.hset(key, lease_id, f"{now_s:.6f}")
        pipe.hlen(key)
        # Keep the hash-wide TTL well above lease_ttl so an idle key eventually
        # expires but the reaper is the primary cleanup mechanism.
        pipe.pexpire(key, int(self._lease_ttl * 1000 * 10))
        results = await pipe.execute()
        occupancy = int(results[1])
        if occupancy <= limit:
            return lease_id
        # Too many holders — roll back our field.
        await self._client.hdel(key, lease_id)
        return None

    async def acquire(self, name: str, limit: int, max_wait: float) -> object | None:
        start = time.monotonic()
        lease_id = await self._try_acquire_once(name, limit)
        if lease_id is not None:
            return lease_id
        if max_wait <= 0.0:
            raise BulkheadFullError(name, limit, waited=0.0)
        deadline = start + max_wait
        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)
            lease_id = await self._try_acquire_once(name, limit)
            if lease_id is not None:
                return lease_id
        raise BulkheadFullError(name, limit, waited=time.monotonic() - start)

    async def release(self, name: str, token: object | None) -> None:
        if not isinstance(token, str):
            raise TypeError(
                f"RedisBulkheadBackend.release expected lease_id str, got {type(token).__name__}"
            )
        await self._client.hdel(self._key(name), token)

    async def reap_expired_leases(self, name: str) -> int:
        """Delete lease fields older than ``lease_ttl``. Return count reaped."""
        key = self._key(name)
        cutoff = time.time() - self._lease_ttl
        fields: dict[bytes, bytes] = await self._client.hgetall(key)
        stale: list[bytes] = []
        for lease_id, ts_bytes in fields.items():
            try:
                ts = float(ts_bytes)
            except (TypeError, ValueError):
                stale.append(lease_id)
                continue
            if ts < cutoff:
                stale.append(lease_id)
        if not stale:
            return 0
        await self._client.hdel(key, *stale)
        return len(stale)


__all__ = ["RedisBulkheadBackend"]
