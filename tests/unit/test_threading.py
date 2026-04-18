"""Tests for ``hawkapi._threading`` — PEP 703 detection + null-lock helpers."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import threading

import pytest

from hawkapi import _threading


def test_free_threaded_matches_is_gil_enabled() -> None:
    """``FREE_THREADED`` must reflect the interpreter's actual GIL state."""
    is_gil_enabled = getattr(sys, "_is_gil_enabled", None)
    if is_gil_enabled is None:
        assert _threading.FREE_THREADED is False
    else:
        assert _threading.FREE_THREADED is (not is_gil_enabled())


def test_maybe_thread_lock_returns_nullcontext_under_gil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", False)
    ctx = _threading.maybe_thread_lock()
    assert isinstance(ctx, contextlib.nullcontext)
    with ctx:
        pass  # no-op must not raise


def test_maybe_thread_lock_returns_real_lock_under_free_threaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", True)
    lock = _threading.maybe_thread_lock()
    assert isinstance(lock, type(threading.Lock()))
    with lock:
        pass


async def test_maybe_async_lock_is_noop_under_gil(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Null async lock: full ``asyncio.Lock`` protocol, all no-op."""
    monkeypatch.setattr(_threading, "FREE_THREADED", False)
    lock = _threading.maybe_async_lock()

    # Context-manager path.
    async with lock:
        pass

    # Direct acquire / release / locked — must all behave as no-ops and never
    # report the lock as held.
    assert await lock.acquire() is True
    assert lock.locked() is False
    lock.release()
    assert lock.locked() is False


async def test_maybe_async_lock_returns_real_lock_under_free_threaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_threading, "FREE_THREADED", True)
    lock = _threading.maybe_async_lock()
    assert isinstance(lock, asyncio.Lock)
    async with lock:
        assert lock.locked() is True
    assert lock.locked() is False


def test_detect_free_threaded_handles_missing_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On interpreters without ``sys._is_gil_enabled``, detection returns False."""
    monkeypatch.delattr(sys, "_is_gil_enabled", raising=False)
    fresh = importlib.reload(_threading)
    try:
        assert fresh.FREE_THREADED is False
    finally:
        importlib.reload(_threading)  # restore original module state
