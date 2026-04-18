"""Bulkhead performance benchmark — local backend acquire/release overhead."""

from __future__ import annotations

import asyncio

import pytest

from hawkapi.middleware.bulkhead import Bulkhead


@pytest.mark.perf
@pytest.mark.benchmark(group="bulkhead")
def test_bulkhead_acquire_release_local(benchmark) -> None:
    bh = Bulkhead("perf", limit=100)

    async def one_round_trip() -> None:
        async with bh:
            pass

    def run() -> None:
        asyncio.run(one_round_trip())

    benchmark(run)
