"""Free-threaded Python (PEP 703) detection and conditional lock helpers.

CPython 3.13+ ships an experimental free-threaded build (``python3.13t``) that
runs without the Global Interpreter Lock. Under that build, even simple
operations such as ``dict[key] = value`` or ``self.counter += 1`` can race
between OS threads, so any module with shared mutable state must guard those
mutations with an explicit lock.

Under the regular GIL build, these locks add latency to a hot path that is
already serialised by the interpreter, so we want to skip them entirely. This
module exposes:

* :data:`FREE_THREADED` — ``True`` only on a no-GIL CPython 3.13+ build.
* :func:`maybe_thread_lock` — returns a real ``threading.Lock`` on a
  free-threaded build, otherwise a no-op context manager whose ``__enter__``
  and ``__exit__`` collapse to a few microseconds of overhead.
* :func:`maybe_async_lock` — same idea for ``asyncio.Lock``: returns a real
  lock on free-threaded builds, otherwise a no-op async context manager.

The detection follows the PEP 703 reference: ``sys._is_gil_enabled()`` exists
on 3.13+ and returns ``False`` when the interpreter is running without the
GIL. We never call ``sys._is_gil_enabled`` on older interpreters because the
attribute does not exist there.
"""

from __future__ import annotations

import contextlib
import sys
import threading
from typing import Any


def _detect_free_threaded() -> bool:
    """Return ``True`` only on a CPython 3.13+ free-threaded (no-GIL) build."""
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_gil_enabled is None:
        return False
    try:
        return not is_gil_enabled()
    except Exception:
        return False


#: ``True`` when running on a free-threaded (PEP 703) CPython build.
FREE_THREADED: bool = _detect_free_threaded()


class _NullAsyncLock:
    """Async no-op lock — drop-in replacement for ``asyncio.Lock`` under GIL."""

    __slots__ = ()

    async def __aenter__(self) -> _NullAsyncLock:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def acquire(self) -> bool:
        return True

    def release(self) -> None:
        return None

    def locked(self) -> bool:
        return False


def maybe_thread_lock() -> threading.Lock | contextlib.AbstractContextManager[Any]:
    """Return a real ``threading.Lock`` on free-threaded builds, else a no-op.

    The no-op variant is :class:`contextlib.nullcontext`, which costs roughly
    one attribute lookup per ``with`` statement under the GIL build.
    """
    if FREE_THREADED:
        return threading.Lock()
    return contextlib.nullcontext()


def maybe_async_lock() -> Any:
    """Return a real ``asyncio.Lock`` on free-threaded builds, else a no-op.

    Imported lazily so this module stays import-cheap and free of asyncio at
    interpreter start-up.
    """
    if FREE_THREADED:
        import asyncio

        return asyncio.Lock()
    return _NullAsyncLock()


__all__ = [
    "FREE_THREADED",
    "maybe_async_lock",
    "maybe_thread_lock",
]
