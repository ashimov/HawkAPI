"""Redis-backed rate limiting middleware using token bucket algorithm."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware

logger = logging.getLogger("hawkapi.rate_limit_redis")

# Lua script for atomic token bucket operation.
# Keys: [bucket_key]
# Args: [burst, rate, now]
# Returns: [allowed (0/1), retry_after (float as string)]
_BUCKET_SCRIPT = """
local key = KEYS[1]
local burst = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local tokens = burst
local last_refill = now

local exists = redis.call('EXISTS', key)
if exists == 1 then
    tokens = tonumber(redis.call('HGET', key, 'tokens'))
    last_refill = tonumber(redis.call('HGET', key, 'last_refill'))
end

-- Refill tokens
local elapsed = now - last_refill
tokens = math.min(burst, tokens + elapsed * rate)
last_refill = now

-- Try to consume
if tokens >= 1.0 then
    tokens = tokens - 1.0
    redis.call('HSET', key, 'tokens', tostring(tokens), 'last_refill', tostring(last_refill))
    redis.call('EXPIRE', key, math.ceil(burst / rate) + 60)
    return {1, "0"}
else
    redis.call('HSET', key, 'tokens', tostring(tokens), 'last_refill', tostring(last_refill))
    redis.call('EXPIRE', key, math.ceil(burst / rate) + 60)
    local retry_after = (1.0 - tokens) / rate
    return {0, tostring(retry_after)}
end
"""


class RedisRateLimitMiddleware(Middleware):
    """Redis-backed rate limiter using token bucket algorithm.

    Requires: pip install redis (or hawkapi[redis])
    Survives restarts, works across multiple processes.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        redis_url: str = "redis://localhost:6379",
        requests_per_second: float = 10.0,
        burst: int = 0,
        key_func: Callable[[Scope], str] | None = None,
        key_prefix: str = "hawkapi:rl:",
    ) -> None:
        super().__init__(app)
        self.rate = requests_per_second
        self.burst = burst if burst > 0 else int(requests_per_second)
        self.key_func = key_func or _default_key_func
        self.key_prefix = key_prefix

        self._redis_url = redis_url
        self._redis_client: object | None = None
        self._lua_sha: str | None = None
        self._redis_available = True
        self._init_lock = asyncio.Lock()

        # In-memory fallback state
        self._fallback_buckets: dict[str, list[float]] = {}
        self._fallback_lock = asyncio.Lock()

    async def _get_redis(self) -> object | None:
        """Lazily initialize the Redis client."""
        if self._redis_client is not None:
            return self._redis_client

        async with self._init_lock:
            if self._redis_client is not None:
                return self._redis_client

            try:
                import redis.asyncio as aioredis  # pyright: ignore[reportMissingImports]

                client = aioredis.from_url(self._redis_url)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                await client.ping()  # pyright: ignore[reportUnknownMemberType,reportGeneralTypeIssues]
                self._lua_sha = await client.script_load(_BUCKET_SCRIPT)  # pyright: ignore[reportUnknownMemberType,reportGeneralTypeIssues]
                self._redis_client = client  # pyright: ignore[reportUnknownVariableType]
                return client  # pyright: ignore[reportReturnType,reportUnknownVariableType]
            except Exception:
                logger.warning(
                    "Redis unavailable at %s, falling back to in-memory rate limiting",
                    self._redis_url,
                )
                self._redis_available = False
                return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self.key_func(scope)

        if self._redis_available:
            allowed, retry_after = await self._check_redis(key)
        else:
            allowed, retry_after = await self._check_fallback(key)

        if allowed:
            await self.app(scope, receive, send)
        else:
            await _send_429(send, retry_after)

    async def _check_redis(self, key: str) -> tuple[bool, float]:
        """Check rate limit using Redis."""
        try:
            client = await self._get_redis()
            if client is None:
                return await self._check_fallback(key)

            redis_key = f"{self.key_prefix}{key}"
            now = time.time()

            result: list[Any] = await client.evalsha(  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportGeneralTypeIssues,reportUnknownVariableType]
                self._lua_sha,  # pyright: ignore[reportArgumentType]
                1,
                redis_key,
                str(self.burst),
                str(self.rate),
                str(now),
            )

            allowed = int(result[0]) == 1  # pyright: ignore[reportUnknownArgumentType,reportIndexIssue]
            retry_after = float(result[1])  # pyright: ignore[reportUnknownArgumentType,reportIndexIssue]
            return allowed, retry_after

        except Exception:
            logger.warning("Redis error during rate limit check, falling back to in-memory")
            self._redis_available = False
            return await self._check_fallback(key)

    async def _check_fallback(self, key: str) -> tuple[bool, float]:
        """In-memory fallback when Redis is unavailable."""
        async with self._fallback_lock:
            now = time.monotonic()

            if key not in self._fallback_buckets:
                self._fallback_buckets[key] = [float(self.burst), now]

            bucket = self._fallback_buckets[key]
            elapsed = now - bucket[1]
            bucket[1] = now
            bucket[0] = min(float(self.burst), bucket[0] + elapsed * self.rate)

            if bucket[0] >= 1.0:
                bucket[0] -= 1.0
                return True, 0.0
            else:
                retry_after = (1.0 - bucket[0]) / self.rate
                return False, retry_after


async def _send_429(send: Send, retry_after: float) -> None:
    """Send a 429 Too Many Requests response."""
    body = b'{"detail":"Too Many Requests"}'
    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
                (b"retry-after", str(int(retry_after) + 1).encode("latin-1")),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
        }
    )


def _default_key_func(scope: Scope) -> str:
    """Default key: client IP address."""
    client = scope.get("client")
    if client:
        return client[0]
    return "unknown"
