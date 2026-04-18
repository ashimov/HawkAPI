"""Redis-backed circuit breaker middleware (distributed three-state pattern).

Tracks failures per path in Redis so circuit state is shared across all
application instances/pods.  When *failure_threshold* consecutive failures
occur the circuit opens globally and subsequent requests on every pod are
rejected with 503.  After *recovery_timeout* seconds the circuit transitions
to HALF_OPEN and allows up to *half_open_max_calls* probe requests through.
If a probe succeeds the circuit closes; if a probe fails the circuit re-opens.

State transitions are performed via Lua scripts for atomicity, preventing
race conditions across pods.  Falls back to in-memory state if Redis is
unavailable (per-process only — same semantics as ``CircuitBreakerMiddleware``).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.serialization.encoder import encode_response

logger = logging.getLogger("hawkapi.circuit_breaker_redis")

# Lua script that checks current circuit state and atomically decides whether
# to allow a request through.
#
# Keys: [circuit_key]
# Args: [now, recovery_timeout, half_open_max_calls]
# Returns: [allowed (0/1), state_after ("CLOSED"|"OPEN"|"HALF_OPEN")]
_CHECK_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local recovery_timeout = tonumber(ARGV[2])
local half_open_max = tonumber(ARGV[3])

local state = redis.call('HGET', key, 'state')
if not state then
    state = 'CLOSED'
end

if state == 'OPEN' then
    local opened_at = tonumber(redis.call('HGET', key, 'opened_at') or '0')
    if (now - opened_at) >= recovery_timeout then
        -- Transition to HALF_OPEN and grant first probe
        redis.call('HSET', key, 'state', 'HALF_OPEN', 'half_open_calls', '1')
        return {1, 'HALF_OPEN'}
    else
        return {0, 'OPEN'}
    end
end

if state == 'HALF_OPEN' then
    local calls = tonumber(redis.call('HGET', key, 'half_open_calls') or '0')
    if calls >= half_open_max then
        return {0, 'HALF_OPEN'}
    end
    redis.call('HINCRBY', key, 'half_open_calls', 1)
    return {1, 'HALF_OPEN'}
end

-- CLOSED — pass through
return {1, 'CLOSED'}
"""

# Lua script that records the outcome of a request and atomically updates state.
#
# Keys: [circuit_key]
# Args: [now, success (0/1), failure_threshold]
# Returns: state_after ("CLOSED"|"OPEN"|"HALF_OPEN")
_RECORD_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local success = tonumber(ARGV[2])
local failure_threshold = tonumber(ARGV[3])

local state = redis.call('HGET', key, 'state') or 'CLOSED'

if success == 1 then
    -- Success: close the circuit and reset counters.
    redis.call('HSET', key, 'state', 'CLOSED',
        'failure_count', '0', 'half_open_calls', '0', 'opened_at', '0')
    return 'CLOSED'
end

-- Failure path
if state == 'HALF_OPEN' then
    -- Probe failed — re-open immediately
    redis.call('HSET', key, 'state', 'OPEN',
        'opened_at', tostring(now), 'half_open_calls', '0')
    return 'OPEN'
end

local failures = redis.call('HINCRBY', key, 'failure_count', 1)
if failures >= failure_threshold then
    redis.call('HSET', key, 'state', 'OPEN', 'opened_at', tostring(now))
    return 'OPEN'
end
return state
"""


class _LocalCircuitState:
    """Per-path mutable state used by the in-memory fallback path."""

    __slots__ = ("state", "failure_count", "opened_at", "half_open_calls")

    def __init__(self) -> None:
        self.state: str = "CLOSED"
        self.failure_count: int = 0
        self.opened_at: float = 0.0
        self.half_open_calls: int = 0


class RedisCircuitBreakerMiddleware(Middleware):
    """Distributed three-state circuit breaker backed by Redis.

    Requires: ``pip install redis`` (or ``hawkapi[redis]``).
    Survives restarts and works across multiple processes/pods.

    Falls back to per-process in-memory state if Redis is unavailable so the
    application keeps serving traffic even when the central store goes down.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "hawkapi:cb:",
    ) -> None:
        super().__init__(app)
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.key_prefix = key_prefix

        self._redis_url = redis_url
        self._redis_client: object | None = None
        self._check_sha: str | None = None
        self._record_sha: str | None = None
        self._redis_available = True
        self._init_lock = asyncio.Lock()

        # In-memory fallback state — same shape as the in-memory middleware.
        self._fallback_circuits: dict[str, _LocalCircuitState] = {}
        self._fallback_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Redis bootstrap
    # ------------------------------------------------------------------

    async def _get_redis(self) -> object | None:
        """Lazily initialize the Redis client and load Lua scripts."""
        if self._redis_client is not None:
            return self._redis_client

        async with self._init_lock:
            if self._redis_client is not None:
                return self._redis_client

            try:
                import redis.asyncio as aioredis  # pyright: ignore[reportMissingImports]

                client = aioredis.from_url(self._redis_url)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                await client.ping()  # pyright: ignore[reportUnknownMemberType,reportGeneralTypeIssues]
                self._check_sha = await client.script_load(_CHECK_SCRIPT)  # pyright: ignore[reportUnknownMemberType,reportGeneralTypeIssues]
                self._record_sha = await client.script_load(_RECORD_SCRIPT)  # pyright: ignore[reportUnknownMemberType,reportGeneralTypeIssues]
                self._redis_client = client  # pyright: ignore[reportUnknownVariableType]
                return client  # pyright: ignore[reportReturnType,reportUnknownVariableType]
            except Exception:
                logger.warning(
                    "Redis unavailable at %s, falling back to in-memory circuit breaker",
                    self._redis_url,
                )
                self._redis_available = False
                return None

    # ------------------------------------------------------------------
    # ASGI entry point
    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")

        if self._redis_available:
            allowed = await self._check_redis(path)
        else:
            allowed = await self._check_fallback(path)

        if not allowed:
            await self._send_503(send, path)
            return

        # --- Forward to inner app, capturing the status code ---
        status_code: int | None = None

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        except Exception:
            await self._record(path, success=False)
            raise

        if status_code is None:
            return
        if status_code >= 500:
            await self._record(path, success=False)
        else:
            await self._record(path, success=True)

    # ------------------------------------------------------------------
    # Redis path
    # ------------------------------------------------------------------

    async def _check_redis(self, path: str) -> bool:
        try:
            client = await self._get_redis()
            if client is None:
                return await self._check_fallback(path)

            redis_key = f"{self.key_prefix}{path}"
            now = time.time()

            result: list[Any] = await client.evalsha(  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportGeneralTypeIssues,reportUnknownVariableType]
                self._check_sha,  # pyright: ignore[reportArgumentType]
                1,
                redis_key,
                str(now),
                str(self.recovery_timeout),
                str(self.half_open_max_calls),
            )
            return int(result[0]) == 1  # pyright: ignore[reportUnknownArgumentType,reportIndexIssue]

        except Exception:
            logger.warning("Redis error during circuit breaker check, falling back to in-memory")
            self._redis_available = False
            return await self._check_fallback(path)

    async def _record(self, path: str, *, success: bool) -> None:
        if self._redis_available:
            try:
                client = await self._get_redis()
                if client is None:
                    await self._record_fallback(path, success=success)
                    return

                redis_key = f"{self.key_prefix}{path}"
                now = time.time()
                await client.evalsha(  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue,reportGeneralTypeIssues]
                    self._record_sha,  # pyright: ignore[reportArgumentType]
                    1,
                    redis_key,
                    str(now),
                    "1" if success else "0",
                    str(self.failure_threshold),
                )
                return
            except Exception:
                logger.warning(
                    "Redis error during circuit breaker record, falling back to in-memory"
                )
                self._redis_available = False

        await self._record_fallback(path, success=success)

    # ------------------------------------------------------------------
    # In-memory fallback (mirrors the in-memory middleware semantics)
    # ------------------------------------------------------------------

    async def _check_fallback(self, path: str) -> bool:
        async with self._fallback_lock:
            circuit = self._fallback_circuits.get(path)
            if circuit is None:
                circuit = _LocalCircuitState()
                self._fallback_circuits[path] = circuit

            if circuit.state == "OPEN":
                elapsed = time.monotonic() - circuit.opened_at
                if elapsed >= self.recovery_timeout:
                    circuit.state = "HALF_OPEN"
                    circuit.half_open_calls = 0
                else:
                    return False

            if circuit.state == "HALF_OPEN":
                if circuit.half_open_calls >= self.half_open_max_calls:
                    return False
                circuit.half_open_calls += 1

            return True

    async def _record_fallback(self, path: str, *, success: bool) -> None:
        async with self._fallback_lock:
            circuit = self._fallback_circuits.get(path)
            if circuit is None:
                circuit = _LocalCircuitState()
                self._fallback_circuits[path] = circuit

            if success:
                circuit.state = "CLOSED"
                circuit.failure_count = 0
                circuit.half_open_calls = 0
                return

            if circuit.state == "HALF_OPEN":
                circuit.state = "OPEN"
                circuit.opened_at = time.monotonic()
                circuit.half_open_calls = 0
                return

            circuit.failure_count += 1
            if circuit.failure_count >= self.failure_threshold:
                circuit.state = "OPEN"
                circuit.opened_at = time.monotonic()

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    async def _send_503(self, send: Send, path: str) -> None:
        body = encode_response(
            {
                "type": "https://hawkapi.ashimov.com/errors/circuit-open",
                "title": "Service Unavailable",
                "status": 503,
                "detail": f"Circuit breaker is open for {path}",
            }
        )
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
