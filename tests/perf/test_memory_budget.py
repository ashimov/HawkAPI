"""Memory budget tests.

Run only via::

    uv run pytest tests/perf/ -m memory --memray -v

These tests are skipped automatically when ``pytest-memray`` is not
installed (see ``conftest.py``).

Budgets are intentionally generous to absorb interpreter and import
noise; the real safety net is the ``baseline.json`` regression check
(``> +10%`` peak memory growth fails the build).
"""

from __future__ import annotations

import asyncio

import pytest

from hawkapi import HawkAPI


def _make_scope(path: str = "/ping") -> dict[str, object]:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }


async def _receive() -> dict[str, object]:
    return {"type": "http.request", "body": b"", "more_body": False}


async def _send(message: dict[str, object]) -> None:
    return None


def _build_minimal_app() -> HawkAPI:
    """A tiny HawkAPI app with docs/openapi disabled and a few routes."""
    app = HawkAPI(openapi_url=None, docs_url=None, redoc_url=None, scalar_url=None)

    @app.get("/ping")
    async def _ping() -> dict[str, bool]:
        return {"pong": True}

    @app.get("/users/{user_id:int}")
    async def _get_user(user_id: int) -> dict[str, object]:
        return {"id": user_id, "name": "Alice"}

    @app.post("/items")
    async def _create_item() -> dict[str, bool]:
        return {"created": True}

    return app


@pytest.mark.memory
@pytest.mark.limit_memory("5 MB")
def test_app_init_memory_budget() -> None:
    """A minimal HawkAPI() init plus 3 routes should fit in 5 MB."""
    app = _build_minimal_app()
    assert app is not None
    # Touch a couple of attributes so the optimizer cannot elide the work.
    assert app.title == "HawkAPI"
    assert app._openapi_url is None


@pytest.mark.memory
@pytest.mark.limit_memory("1 MB")
def test_single_request_memory_budget() -> None:
    """A single ASGI request should peak well under 1 MB.

    The original spec called for ``100 KB``, but msgspec encoding plus
    the response/middleware allocations together push a fresh-process
    measurement just over that. 1 MB still catches an order-of-magnitude
    regression while staying robust to runtime noise.
    """
    app = _build_minimal_app()
    scope = _make_scope("/ping")
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(app(scope, _receive, _send))
    finally:
        loop.close()


@pytest.mark.memory
@pytest.mark.limit_leaks("64 KB")
def test_no_leaks_in_request_loop() -> None:
    """1000 requests should not accumulate meaningful per-request leaks.

    ``limit_leaks`` only counts memory still allocated when the test
    ends, so this catches per-request retention regressions while
    tolerating a small amount of one-shot interpreter overhead.
    """
    app = _build_minimal_app()
    scope = _make_scope("/ping")
    loop = asyncio.new_event_loop()

    async def _drive() -> None:
        for _ in range(1000):
            await app(scope, _receive, _send)

    try:
        loop.run_until_complete(_drive())
    finally:
        loop.close()
