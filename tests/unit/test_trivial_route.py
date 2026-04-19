"""Unit tests for the trivial-route fast-path classification.

Verifies that ``route._is_trivial`` is True for simple async handlers that
return a Response directly, and False whenever any feature that requires the
full ``_execute_route`` path is present (DI, deps, perms, bg-tasks, etc.).

NOTE: This file intentionally omits ``from __future__ import annotations``.
PEP 563 (postponed evaluation) stringifies all annotations, which prevents
``get_type_hints()`` from resolving ``Depends(closure_var)`` markers on
handlers defined inside class methods. Without the import, annotations are
evaluated eagerly so the plan builder sees real objects.
"""

from typing import Annotated

from hawkapi import HawkAPI
from hawkapi.background import BackgroundTasks
from hawkapi.di.depends import Depends
from hawkapi.requests.request import Request
from hawkapi.responses.json_response import JSONResponse
from hawkapi.responses.plain_text import PlainTextResponse
from hawkapi.responses.response import Response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_route(app: HawkAPI, path: str) -> object:
    """Return the registered route for *path*."""
    for route in app.routes:
        if route.path == path:
            return route
    raise KeyError(f"No route registered at {path!r}")


# ---------------------------------------------------------------------------
# Trivial = True cases
# ---------------------------------------------------------------------------


class TestTrivialTrue:
    def test_no_arg_async_handler(self) -> None:
        """Async handler with no parameters is trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/ping")
        async def handler() -> Response:
            return Response(b"pong")

        route = _get_route(app, "/ping")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

    def test_request_only_param(self) -> None:
        """Handler that only takes Request is trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/hello")
        async def handler(request: Request) -> Response:
            return PlainTextResponse("hi")

        route = _get_route(app, "/hello")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

    def test_path_param_only(self) -> None:
        """Handler with a single path param is trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/items/{item_id}")
        async def handler(item_id: str) -> Response:
            return Response(item_id.encode())

        route = _get_route(app, "/items/{item_id}")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

    def test_query_param_with_default(self) -> None:
        """Handler with a plain query param default is trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/search")
        async def handler(q: str = "") -> Response:
            return Response(q.encode())

        route = _get_route(app, "/search")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

    def test_json_response_return(self) -> None:
        """Handler returning JSONResponse is trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/data")
        async def handler() -> JSONResponse:
            return JSONResponse({"ok": True})

        route = _get_route(app, "/data")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Trivial = False cases
# ---------------------------------------------------------------------------


class TestTrivialFalse:
    def test_sync_handler_not_trivial(self) -> None:
        """Sync (non-async) handlers cannot use the fast path."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/sync")
        def handler() -> Response:  # type: ignore[return]
            return Response(b"sync")

        route = _get_route(app, "/sync")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_depends_callable_not_trivial(self) -> None:
        """Routes with Depends() callable injection are NOT trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        async def my_dep() -> str:
            return "dep_value"

        @app.get("/dep")
        async def handler(val: Annotated[str, Depends(my_dep)]) -> Response:
            return Response(val.encode())

        route = _get_route(app, "/dep")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_permissions_not_trivial(self) -> None:
        """Routes with permissions are NOT trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/secure", permissions=["admin"])
        async def handler() -> Response:
            return Response(b"secure")

        route = _get_route(app, "/secure")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_route_level_dependencies_not_trivial(self) -> None:
        """Routes with side-effect dependencies=[Depends(...)] are NOT trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        async def auth_guard() -> None:
            pass

        @app.get("/guarded", dependencies=[Depends(auth_guard)])
        async def handler() -> Response:
            return Response(b"guarded")

        route = _get_route(app, "/guarded")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_background_tasks_not_trivial(self) -> None:
        """Routes injecting BackgroundTasks are NOT trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/bg")
        async def handler(bg: BackgroundTasks) -> Response:
            return Response(b"bg")

        route = _get_route(app, "/bg")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_response_model_not_trivial(self) -> None:
        """Routes with an explicit response_model are NOT trivial."""
        import msgspec

        app = HawkAPI(openapi_url=None, health_url=None)

        class Item(msgspec.Struct):
            name: str

        @app.get("/item", response_model=Item)
        async def handler() -> Item:
            return Item(name="x")

        route = _get_route(app, "/item")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_deprecated_not_trivial(self) -> None:
        """Deprecated routes are NOT trivial (need deprecation headers)."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/old", deprecated=True)
        async def handler() -> Response:
            return Response(b"old")

        route = _get_route(app, "/old")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]

    def test_exclude_none_not_trivial(self) -> None:
        """Routes with response_model_exclude_none are NOT trivial."""
        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/filtered", response_model_exclude_none=True)
        async def handler() -> dict:  # type: ignore[return]
            return {"a": 1, "b": None}

        route = _get_route(app, "/filtered")
        assert route._is_trivial is False  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# End-to-end: trivial fast path produces correct HTTP responses
# ---------------------------------------------------------------------------


class TestTrivialFastPathE2E:
    def test_plaintext_response_via_fast_path(self) -> None:
        """The trivial fast path returns the correct status + body."""
        from hawkapi.testing import TestClient

        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/hello")
        async def handler() -> Response:
            return PlainTextResponse("Hello, World!")

        route = _get_route(app, "/hello")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

        client = TestClient(app)
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert resp.text == "Hello, World!"

    def test_request_param_via_fast_path(self) -> None:
        """Trivial route correctly receives the Request object."""
        from hawkapi.testing import TestClient

        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/echo-path")
        async def handler(request: Request) -> Response:
            return PlainTextResponse(request.path)

        route = _get_route(app, "/echo-path")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

        client = TestClient(app)
        resp = client.get("/echo-path")
        assert resp.text == "/echo-path"

    def test_query_param_via_fast_path(self) -> None:
        """Trivial route correctly resolves a query string parameter."""
        from hawkapi.testing import TestClient

        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/greet")
        async def handler(name: str = "world") -> Response:
            return PlainTextResponse(f"hello {name}")

        route = _get_route(app, "/greet")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

        client = TestClient(app)
        assert client.get("/greet").text == "hello world"
        assert client.get("/greet?name=hawk").text == "hello hawk"

    def test_http_exception_via_fast_path(self) -> None:
        """HTTPException raised in a trivial handler is handled correctly."""
        from hawkapi.exceptions import HTTPException
        from hawkapi.testing import TestClient

        app = HawkAPI(openapi_url=None, health_url=None)

        @app.get("/fail")
        async def handler() -> Response:
            raise HTTPException(status_code=403, detail="Forbidden")

        route = _get_route(app, "/fail")
        assert route._is_trivial is True  # pyright: ignore[reportPrivateUsage]

        client = TestClient(app)
        resp = client.get("/fail")
        assert resp.status_code == 403
