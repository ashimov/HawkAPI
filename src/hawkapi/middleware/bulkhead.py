"""Hystrix-style bulkhead — named, size-limited async concurrency isolator.

Complement to ``AdaptiveConcurrencyMiddleware`` (global auto-tuned cap) and
``RateLimit*`` middleware (time-windowed budget). A ``Bulkhead`` partitions
capacity across *named* resource pools so saturation of one pool does not
starve others.

Two public forms share one implementation:

* Context manager ``async with Bulkhead("stripe", limit=10): ...``
* Decorator ``@bulkhead("payments", limit=10)`` — rejects over-limit
  requests with HTTP 503 + ``Retry-After``.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from functools import wraps
from typing import Any, Protocol, TypeVar

from hawkapi.exceptions import HTTPException


class BulkheadFullError(Exception):
    """Raised when a Bulkhead has no free slot within the wait budget."""

    def __init__(self, name: str, limit: int, waited: float) -> None:
        super().__init__(f"bulkhead {name!r} full (limit={limit}, waited={waited:.3f}s)")
        self.name = name
        self.limit = limit
        self.waited = waited


class BulkheadBackend(Protocol):
    """Pluggable concurrency backend."""

    async def acquire(self, name: str, limit: int, max_wait: float) -> object | None: ...

    async def release(self, name: str, token: object | None) -> None: ...


class LocalBulkheadBackend:
    """In-process backend — one ``asyncio.Semaphore`` per name.

    Safe for concurrent use across tasks. Collisions (same name, different
    ``limit``) raise ``ValueError`` at acquire time — the first ``limit`` wins.
    """

    def __init__(self) -> None:
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._limits: dict[str, int] = {}
        # Guards the two dicts during first-time registration only. After a
        # name is registered, ``acquire`` takes the lock-free fast path.
        self._register_lock = asyncio.Lock()

    async def _get_semaphore(self, name: str, limit: int) -> asyncio.Semaphore:
        sem = self._semaphores.get(name)
        if sem is not None:
            if self._limits[name] != limit:
                raise ValueError(
                    f"bulkhead {name!r} already registered with "
                    f"limit={self._limits[name]}, got limit={limit}"
                )
            return sem
        async with self._register_lock:
            sem = self._semaphores.get(name)
            if sem is not None:
                if self._limits[name] != limit:
                    raise ValueError(
                        f"bulkhead {name!r} already registered with "
                        f"limit={self._limits[name]}, got limit={limit}"
                    )
                return sem
            sem = asyncio.Semaphore(limit)
            self._semaphores[name] = sem
            self._limits[name] = limit
            return sem

    async def acquire(self, name: str, limit: int, max_wait: float) -> object | None:
        sem = await self._get_semaphore(name, limit)
        if max_wait <= 0.0:
            # Non-blocking acquire: ``asyncio.timeout(0)`` yields control once,
            # then fails if the semaphore is still blocked.
            try:
                async with asyncio.timeout(0):
                    await sem.acquire()
            except TimeoutError:
                raise BulkheadFullError(name, limit, waited=0.0) from None
            return None
        start = time.monotonic()
        try:
            async with asyncio.timeout(max_wait):
                await sem.acquire()
        except TimeoutError:
            waited = time.monotonic() - start
            raise BulkheadFullError(name, limit, waited=waited) from None
        return None

    async def release(self, name: str, token: object | None) -> None:
        sem = self._semaphores.get(name)
        if sem is None:
            raise RuntimeError(f"release of unregistered bulkhead {name!r}")
        sem.release()


# Module-level default backend shared across all Bulkhead instances that do
# not explicitly pass their own.
_DEFAULT_LOCAL_BACKEND: LocalBulkheadBackend = LocalBulkheadBackend()

# Per-task stack of acquired tokens, keyed by bulkhead name. A list — not a
# single token — so nested same-name acquires in one task work correctly.
_TOKEN_STACKS: ContextVar[dict[str, list[object | None]] | None] = ContextVar(
    "hawkapi_bulkhead_tokens", default=None
)


def _push_token(name: str, token: object | None) -> None:
    stacks = _TOKEN_STACKS.get()
    if stacks is None:
        # First use in this task — create a fresh dict for isolated ownership.
        stacks = {}
        _TOKEN_STACKS.set(stacks)
    elif not stacks.get(name):
        # The dict may be inherited from a parent task (asyncio.create_task
        # copies the Context but not the mutable dict inside). If we do not
        # yet have a stack for this name, fork a per-task copy so our pushes
        # don't clobber the parent's stacks.
        # (If we already have a non-empty stack for this name, we're nested
        # in our own task and should keep mutating it.)
        stacks = dict(stacks)
        stacks[name] = []
        _TOKEN_STACKS.set(stacks)
    stacks.setdefault(name, []).append(token)


def _pop_token(name: str) -> object | None:
    stacks = _TOKEN_STACKS.get()
    if stacks is None or not stacks.get(name):
        raise RuntimeError(
            f"unpaired bulkhead release for {name!r} — this usually means "
            "release was called outside the task that acquired the slot"
        )
    token = stacks[name].pop()
    if not stacks[name]:
        del stacks[name]
    return token


class Bulkhead:
    """Named, size-limited async concurrency isolator.

    Usage::

        bh = Bulkhead("stripe", limit=10, max_wait=0.5)
        async with bh:
            await stripe_client.charge(...)

    The same instance is safe to share across tasks; per-acquire state lives
    in a task-local ``ContextVar``.
    """

    __slots__ = ("_name", "_limit", "_max_wait", "_backend")

    def __init__(
        self,
        name: str,
        limit: int,
        max_wait: float = 0.0,
        *,
        backend: BulkheadBackend | None = None,
    ) -> None:
        if limit < 1:
            raise ValueError(f"limit must be >= 1, got {limit}")
        if max_wait < 0:
            raise ValueError(f"max_wait must be >= 0, got {max_wait}")
        self._name = name
        self._limit = limit
        self._max_wait = max_wait
        self._backend: BulkheadBackend = backend or _DEFAULT_LOCAL_BACKEND

    async def __aenter__(self) -> Bulkhead:
        token = await self._backend.acquire(self._name, self._limit, self._max_wait)
        _push_token(self._name, token)
        return self

    async def __aexit__(self, exc_type: object, exc: BaseException | None, tb: object) -> None:
        token = _pop_token(self._name)
        try:
            await self._backend.release(self._name, token)
        except Exception as release_exc:
            # Body-raised exception takes priority; chain release failure
            # as its __cause__ so both are visible in tracebacks.
            if exc is not None:
                raise release_exc from exc
            raise

    @property
    def name(self) -> str:
        return self._name

    @property
    def limit(self) -> int:
        return self._limit


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def bulkhead(
    name: str,
    limit: int,
    max_wait: float = 0.0,
    *,
    backend: BulkheadBackend | None = None,
    status_code: int = 503,
    retry_after: float = 1.0,
) -> Callable[[F], F]:
    """Decorate an async handler so it acquires a bulkhead slot per call.

    On rejection, the wrapped handler raises ``HTTPException`` with the
    configured ``status_code`` (default 503) and a ``Retry-After`` header
    (default 1.0 s, rounded up to an integer per RFC 9110).
    """
    if retry_after < 0:
        raise ValueError(f"retry_after must be >= 0, got {retry_after}")
    retry_after_header = str(max(1, math.ceil(retry_after)))
    bh = Bulkhead(name, limit, max_wait=max_wait, backend=backend)

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                async with bh:
                    return await func(*args, **kwargs)
            except BulkheadFullError as exc:
                raise HTTPException(
                    status_code=status_code,
                    detail="bulkhead_full",
                    headers={"Retry-After": retry_after_header},
                ) from exc

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = [
    "Bulkhead",
    "BulkheadBackend",
    "BulkheadFullError",
    "LocalBulkheadBackend",
    "bulkhead",
]
