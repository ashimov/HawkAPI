"""Performance regression tests for HawkAPI hot paths.

Run via:
    uv run pytest tests/perf/ -m perf --benchmark-only

Compare against committed baseline:
    uv run pytest tests/perf/ -m perf --benchmark-only \
        --benchmark-compare=tests/perf/.benchmark_baseline.json \
        --benchmark-compare-fail=mean:5%

These tests guard the per-request hot paths that drive HawkAPI's headline
throughput numbers. A >5% regression here typically translates to a noticeable
RPS drop in the wrk-based competitive benchmarks.
"""

from __future__ import annotations

import msgspec
import pytest

from hawkapi.di.param_plan import build_handler_plan
from hawkapi.responses.json_response import JSONResponse
from hawkapi.routing._radix_tree import RadixTree
from hawkapi.routing.route import Route
from hawkapi.serialization.encoder import encode_response

pytestmark = pytest.mark.perf


# ---------------------------------------------------------------------------
# Fixtures: build expensive state once per test module
# ---------------------------------------------------------------------------


def _make_handler():
    async def handler():
        return {}

    return handler


@pytest.fixture(scope="module")
def populated_radix_tree() -> RadixTree:
    """Radix tree pre-populated with a realistic REST API surface."""
    tree = RadixTree()
    prefixes = (
        "users",
        "posts",
        "comments",
        "tags",
        "categories",
        "products",
        "orders",
        "payments",
    )
    for prefix in prefixes:
        tree.insert(
            Route(
                path=f"/{prefix}",
                handler=_make_handler(),
                methods=frozenset({"GET", "HEAD"}),
                name=f"list_{prefix}",
            )
        )
        tree.insert(
            Route(
                path=f"/{prefix}",
                handler=_make_handler(),
                methods=frozenset({"POST"}),
                name=f"create_{prefix}",
            )
        )
        tree.insert(
            Route(
                path=f"/{prefix}/{{id:int}}",
                handler=_make_handler(),
                methods=frozenset({"GET", "HEAD"}),
                name=f"get_{prefix}",
            )
        )
        tree.insert(
            Route(
                path=f"/{prefix}/{{id:int}}",
                handler=_make_handler(),
                methods=frozenset({"PUT"}),
                name=f"update_{prefix}",
            )
        )
        tree.insert(
            Route(
                path=f"/{prefix}/{{id:int}}",
                handler=_make_handler(),
                methods=frozenset({"DELETE"}),
                name=f"delete_{prefix}",
            )
        )
    return tree


# ---------------------------------------------------------------------------
# Routing: radix tree lookup
# ---------------------------------------------------------------------------


def test_radix_tree_lookup_static_perf(benchmark, populated_radix_tree: RadixTree) -> None:
    """Static path lookup — the most common case for an API root."""
    result = benchmark(populated_radix_tree.lookup, "/users", "GET")
    assert result is not None


def test_radix_tree_lookup_param_perf(benchmark, populated_radix_tree: RadixTree) -> None:
    """Path-parameter lookup — exercises converter + parameter binding."""
    result = benchmark(populated_radix_tree.lookup, "/users/42", "GET")
    assert result is not None
    assert result.params["id"] == 42


def test_radix_tree_lookup_miss_perf(benchmark, populated_radix_tree: RadixTree) -> None:
    """Lookup miss — must remain cheap (404 path)."""
    result = benchmark(populated_radix_tree.lookup, "/nonexistent", "GET")
    assert result is None


# ---------------------------------------------------------------------------
# DI: handler plan build (once-per-route registration cost)
# ---------------------------------------------------------------------------


async def _typical_handler(user_id: int, limit: int = 10, q: str = "") -> dict[str, object]:
    return {"user_id": user_id, "limit": limit, "q": q}


def test_handler_plan_build_perf(benchmark) -> None:
    """Building HandlerPlan for a typical handler.

    Runs at registration time, not per-request — but registering hundreds of
    routes adds up, and slow plan building hurts cold-start latency.
    """
    path_params = frozenset({"user_id"})
    plan = benchmark(build_handler_plan, _typical_handler, path_params=path_params)
    assert plan.is_async
    assert len(plan.params) == 3


# ---------------------------------------------------------------------------
# Response: header construction
# ---------------------------------------------------------------------------


def test_response_build_headers_fast_path_perf(benchmark) -> None:
    """JSONResponse._build_raw_headers fast path (no user headers).

    This is the per-request hot path for every JSON endpoint.
    """
    response = JSONResponse({"ok": True})
    headers = benchmark(response._build_raw_headers)
    assert (b"content-type", b"application/json") in headers


def test_response_build_headers_with_user_headers_perf(benchmark) -> None:
    """JSONResponse._build_raw_headers with user-supplied headers."""
    response = JSONResponse(
        {"ok": True},
        headers={"X-Request-ID": "abc-123", "Cache-Control": "no-cache"},
    )
    headers = benchmark(response._build_raw_headers)
    assert any(k == b"x-request-id" for k, _ in headers)


# ---------------------------------------------------------------------------
# Serialization: msgspec encode hot path
# ---------------------------------------------------------------------------


_SMALL_DICT: dict[str, object] = {"id": 1, "name": "Alice", "email": "alice@example.com"}


class _UserStruct(msgspec.Struct):
    id: int
    name: str
    email: str
    is_active: bool = True


_SMALL_STRUCT = _UserStruct(id=1, name="Alice", email="alice@example.com")
_MEDIUM_LIST = [{"id": i, "name": f"User {i}", "email": f"user{i}@example.com"} for i in range(100)]


def test_msgspec_encode_dict_perf(benchmark) -> None:
    """encode_response on a small dict — the typical JSON-API response shape."""
    out = benchmark(encode_response, _SMALL_DICT)
    assert isinstance(out, bytes)


def test_msgspec_encode_struct_perf(benchmark) -> None:
    """encode_response on a msgspec.Struct — the recommended fast path."""
    out = benchmark(encode_response, _SMALL_STRUCT)
    assert isinstance(out, bytes)


def test_msgspec_encode_list_perf(benchmark) -> None:
    """encode_response on a 100-item list — paginated-list response shape."""
    out = benchmark(encode_response, _MEDIUM_LIST)
    assert isinstance(out, bytes)
