# Level 2 Production Features Implementation Plan

**Goal:** Add 13 production-grade features across 3 waves — production essentials, contract pipeline, and DX tooling.

**Architecture:** Each feature is self-contained with its own module, test file, and lazy import entry. Middleware follows the raw ASGI `__call__` pattern (override, not hooks) for performance. CLI commands use `argparse` subparsers. All new public symbols go into `__init__.py` lazy imports + `__all__` + `TYPE_CHECKING`.

**Tech Stack:** Python 3.12+, msgspec, pytest, argparse, ipaddress (stdlib), asyncio

---

## Wave 1: Production Essentials

### Task 1: TrustedProxyMiddleware

**Files:**
- Create: `src/hawkapi/middleware/trusted_proxy.py`
- Create: `tests/unit/test_trusted_proxy.py`
- Modify: `src/hawkapi/__init__.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_trusted_proxy.py
"""Tests for trusted proxy middleware."""

import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware


async def _call_app(app, method, path, headers=None, body=b"", client=("127.0.0.1", 8000)):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
        "scheme": "http",
        "client": client,
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestTrustedProxyMiddleware:
    @pytest.mark.asyncio
    async def test_rewrites_client_ip_from_trusted_proxy(self):
        """X-Forwarded-For from trusted proxy overwrites client IP."""
        captured = {}

        app = HawkAPI(openapi_url=None)
        app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["127.0.0.0/8"])

        @app.get("/ip")
        async def get_ip(request):
            captured["client"] = request.client
            return {"ip": request.client[0] if request.client else None}

        await _call_app(
            app,
            "GET",
            "/ip",
            headers=[(b"x-forwarded-for", b"203.0.113.50")],
            client=("127.0.0.1", 8000),
        )
        assert captured["client"][0] == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_ignores_header_from_untrusted_proxy(self):
        """X-Forwarded-For from untrusted source is ignored."""
        captured = {}

        app = HawkAPI(openapi_url=None)
        app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["10.0.0.0/8"])

        @app.get("/ip")
        async def get_ip(request):
            captured["client"] = request.client
            return {"ip": "ok"}

        await _call_app(
            app,
            "GET",
            "/ip",
            headers=[(b"x-forwarded-for", b"203.0.113.50")],
            client=("192.168.1.1", 8000),
        )
        assert captured["client"][0] == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_rewrites_scheme_from_x_forwarded_proto(self):
        """X-Forwarded-Proto from trusted proxy overwrites scheme."""
        captured = {}

        app = HawkAPI(openapi_url=None)
        app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["127.0.0.0/8"])

        @app.get("/scheme")
        async def get_scheme(request):
            captured["scheme"] = request.scope.get("scheme")
            return {"scheme": captured["scheme"]}

        await _call_app(
            app,
            "GET",
            "/scheme",
            headers=[(b"x-forwarded-proto", b"https")],
            client=("127.0.0.1", 8000),
        )
        assert captured["scheme"] == "https"

    @pytest.mark.asyncio
    async def test_multiple_forwarded_for_takes_first(self):
        """With multiple IPs in X-Forwarded-For, takes the leftmost (original client)."""
        captured = {}

        app = HawkAPI(openapi_url=None)
        app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["127.0.0.0/8"])

        @app.get("/ip")
        async def get_ip(request):
            captured["client"] = request.client
            return {"ip": "ok"}

        await _call_app(
            app,
            "GET",
            "/ip",
            headers=[(b"x-forwarded-for", b"203.0.113.50, 70.41.3.18, 150.172.238.178")],
            client=("127.0.0.1", 8000),
        )
        assert captured["client"][0] == "203.0.113.50"

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        """Non-HTTP scopes pass through unchanged."""
        called = []

        async def inner(scope, receive, send):
            called.append(scope["type"])

        middleware = TrustedProxyMiddleware(inner, trusted_proxies=["127.0.0.0/8"])
        await middleware({"type": "websocket"}, None, None)
        assert called == ["websocket"]

    @pytest.mark.asyncio
    async def test_rewrites_host_from_x_forwarded_host(self):
        """X-Forwarded-Host from trusted proxy overwrites host header."""
        captured = {}

        app = HawkAPI(openapi_url=None)
        app.add_middleware(TrustedProxyMiddleware, trusted_proxies=["127.0.0.0/8"])

        @app.get("/host")
        async def get_host(request):
            captured["host"] = request.headers.get("host")
            return {"host": captured["host"]}

        await _call_app(
            app,
            "GET",
            "/host",
            headers=[
                (b"host", b"internal.local"),
                (b"x-forwarded-host", b"api.example.com"),
            ],
            client=("127.0.0.1", 8000),
        )
        assert captured["host"] == "api.example.com"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trusted_proxy.py -v`
Expected: FAIL (module not found)

**Step 3: Write the implementation**

```python
# src/hawkapi/middleware/trusted_proxy.py
"""Trusted proxy middleware — handle X-Forwarded-* headers from known proxies."""

from __future__ import annotations

import ipaddress
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class TrustedProxyMiddleware(Middleware):
    """Rewrite client IP, scheme, and host from trusted proxy headers.

    Only processes X-Forwarded-For, X-Forwarded-Proto, and X-Forwarded-Host
    when the immediate client IP is in the trusted_proxies list.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_proxies: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._networks = [
            ipaddress.ip_network(p, strict=False)
            for p in (trusted_proxies or [])
        ]

    def _is_trusted(self, client_ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(addr in net for net in self._networks)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if not client or not self._is_trusted(client[0]):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        forwarded_for: str | None = None
        forwarded_proto: str | None = None
        forwarded_host: str | None = None

        for key, value in headers:
            lower_key = key.lower()
            if lower_key == b"x-forwarded-for":
                forwarded_for = value.decode("latin-1")
            elif lower_key == b"x-forwarded-proto":
                forwarded_proto = value.decode("latin-1")
            elif lower_key == b"x-forwarded-host":
                forwarded_host = value.decode("latin-1")

        # Mutate scope for downstream
        new_scope: dict[str, Any] = dict(scope)

        if forwarded_for:
            real_ip = forwarded_for.split(",")[0].strip()
            new_scope["client"] = (real_ip, client[1])

        if forwarded_proto:
            new_scope["scheme"] = forwarded_proto.strip().lower()

        if forwarded_host:
            host = forwarded_host.strip()
            new_headers = [
                (k, v) for k, v in headers if k.lower() != b"host"
            ]
            new_headers.append((b"host", host.encode("latin-1")))
            new_scope["headers"] = new_headers

        await self.app(new_scope, receive, send)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_trusted_proxy.py -v`
Expected: PASS (6 tests)

**Step 5: Add lazy import to `__init__.py`**

Add to `_LAZY_IMPORTS`:
```python
"TrustedProxyMiddleware": ("hawkapi.middleware.trusted_proxy", "TrustedProxyMiddleware"),
```

Add to `TYPE_CHECKING` block:
```python
from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware
```

Add `"TrustedProxyMiddleware"` to `__all__` (alphabetically).

**Step 6: Run full test suite**

Run: `uv run pytest tests/ -x -q`
Expected: all tests pass (including `test_cold_start.py::test_lazy_import_works_for_all_exports`)

**Step 7: Commit**

```bash
git add src/hawkapi/middleware/trusted_proxy.py tests/unit/test_trusted_proxy.py src/hawkapi/__init__.py
git commit -m "feat: add TrustedProxyMiddleware for X-Forwarded-* handling"
```

---

### Task 2: RequestLimitsMiddleware

**Files:**
- Create: `src/hawkapi/middleware/request_limits.py`
- Create: `tests/unit/test_request_limits.py`
- Modify: `src/hawkapi/__init__.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_request_limits.py
"""Tests for request limits middleware."""

import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.request_limits import RequestLimitsMiddleware


async def _call_app(app, method, path, headers=None, body=b"", query_string=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestRequestLimitsMiddleware:
    @pytest.mark.asyncio
    async def test_rejects_long_query_string(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(RequestLimitsMiddleware, max_query_length=50)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test", query_string=b"x" * 100)
        assert resp["status"] == 414

    @pytest.mark.asyncio
    async def test_allows_short_query_string(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(RequestLimitsMiddleware, max_query_length=200)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/test", query_string=b"q=hello")
        assert resp["status"] == 200

    @pytest.mark.asyncio
    async def test_rejects_too_many_headers(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(RequestLimitsMiddleware, max_headers_count=5)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        headers = [(f"x-h-{i}".encode(), b"val") for i in range(10)]
        resp = await _call_app(app, "GET", "/test", headers=headers)
        assert resp["status"] == 431

    @pytest.mark.asyncio
    async def test_rejects_oversized_header_value(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(RequestLimitsMiddleware, max_header_size=100)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        headers = [(b"x-big", b"A" * 200)]
        resp = await _call_app(app, "GET", "/test", headers=headers)
        assert resp["status"] == 431

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        called = []

        async def inner(scope, receive, send):
            called.append(True)

        middleware = RequestLimitsMiddleware(inner, max_query_length=10)
        await middleware({"type": "websocket"}, None, None)
        assert called == [True]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_request_limits.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/middleware/request_limits.py
"""Request limits middleware — reject oversized requests early."""

from __future__ import annotations

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.response import Response
from hawkapi.serialization.encoder import encode_response


class RequestLimitsMiddleware(Middleware):
    """Enforce limits on query string length, header count, and header size.

    Rejects requests early (before body parsing) with appropriate HTTP status codes.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_query_length: int = 2048,
        max_headers_count: int = 100,
        max_header_size: int = 8192,
    ) -> None:
        super().__init__(app)
        self._max_query_length = max_query_length
        self._max_headers_count = max_headers_count
        self._max_header_size = max_header_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check query string length
        qs: bytes = scope.get("query_string", b"")
        if len(qs) > self._max_query_length:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/uri-too-long",
                        "title": "URI Too Long",
                        "status": 414,
                        "detail": f"Query string exceeds {self._max_query_length} bytes",
                    }
                ),
                status_code=414,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        # Check headers
        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        if len(headers) > self._max_headers_count:
            response = Response(
                content=encode_response(
                    {
                        "type": "https://hawkapi.ashimov.com/errors/header-fields-too-large",
                        "title": "Request Header Fields Too Large",
                        "status": 431,
                        "detail": f"Request has {len(headers)} headers, max is {self._max_headers_count}",
                    }
                ),
                status_code=431,
                content_type="application/problem+json",
            )
            await response(scope, receive, send)
            return

        for _key, value in headers:
            if len(value) > self._max_header_size:
                response = Response(
                    content=encode_response(
                        {
                            "type": "https://hawkapi.ashimov.com/errors/header-fields-too-large",
                            "title": "Request Header Fields Too Large",
                            "status": 431,
                            "detail": f"Header value exceeds {self._max_header_size} bytes",
                        }
                    ),
                    status_code=431,
                    content_type="application/problem+json",
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_request_limits.py -v`
Expected: PASS (5 tests)

**Step 5: Add lazy import to `__init__.py`**

Add to `_LAZY_IMPORTS`:
```python
"RequestLimitsMiddleware": ("hawkapi.middleware.request_limits", "RequestLimitsMiddleware"),
```

Add to `TYPE_CHECKING` block and `__all__` (alphabetically).

**Step 6: Run full suite + commit**

```bash
uv run pytest tests/ -x -q
git add src/hawkapi/middleware/request_limits.py tests/unit/test_request_limits.py src/hawkapi/__init__.py
git commit -m "feat: add RequestLimitsMiddleware for query/header size limits"
```

---

### Task 3: Health Probes (/readyz + /livez)

**Files:**
- Modify: `src/hawkapi/app.py`
- Create: `tests/unit/test_health_probes.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_health_probes.py
"""Tests for /readyz and /livez health probes."""

import msgspec
import pytest

from hawkapi import HawkAPI


async def _call_app(app, method, path, headers=None, body=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestLivenessProbe:
    @pytest.mark.asyncio
    async def test_livez_returns_200(self):
        app = HawkAPI(openapi_url=None)
        resp = await _call_app(app, "GET", "/livez")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["status"] == "alive"

    @pytest.mark.asyncio
    async def test_livez_disabled(self):
        app = HawkAPI(openapi_url=None, livez_url=None)
        resp = await _call_app(app, "GET", "/livez")
        assert resp["status"] == 404


class TestReadinessProbe:
    @pytest.mark.asyncio
    async def test_readyz_no_checks_returns_ready(self):
        app = HawkAPI(openapi_url=None)
        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["status"] == "ready"

    @pytest.mark.asyncio
    async def test_readyz_with_passing_check(self):
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("database")
        async def check_db():
            return True, "postgres connected"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert body["status"] == "ready"
        assert body["checks"]["database"]["ok"] is True

    @pytest.mark.asyncio
    async def test_readyz_with_failing_check(self):
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("cache")
        async def check_cache():
            return False, "redis connection refused"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 503
        body = msgspec.json.decode(resp["body"])
        assert body["status"] == "not_ready"
        assert body["checks"]["cache"]["ok"] is False

    @pytest.mark.asyncio
    async def test_readyz_disabled(self):
        app = HawkAPI(openapi_url=None, readyz_url=None)
        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 404

    @pytest.mark.asyncio
    async def test_readyz_mixed_checks(self):
        app = HawkAPI(openapi_url=None)

        @app.readiness_check("db")
        async def check_db():
            return True, "ok"

        @app.readiness_check("cache")
        async def check_cache():
            return False, "down"

        resp = await _call_app(app, "GET", "/readyz")
        assert resp["status"] == 503
        body = msgspec.json.decode(resp["body"])
        assert body["checks"]["db"]["ok"] is True
        assert body["checks"]["cache"]["ok"] is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_health_probes.py -v`
Expected: FAIL

**Step 3: Modify `src/hawkapi/app.py`**

Add `readyz_url` and `livez_url` parameters to `__init__`:

```python
# In __init__ signature, add after health_url:
readyz_url: str | None = "/readyz",
livez_url: str | None = "/livez",
```

Add `_readiness_checks` dict and setup calls:

```python
# After self._in_flight = 0
self._readiness_checks: dict[str, Callable[..., Any]] = {}

# After health endpoint setup
if livez_url is not None:
    self._setup_livez_route(livez_url)
if readyz_url is not None:
    self._setup_readyz_route(readyz_url)
```

Add `readiness_check` decorator and route setup methods:

```python
def readiness_check(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a readiness check (decorator)."""
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        self._readiness_checks[name] = func
        return func
    return decorator

def _setup_livez_route(self, livez_url: str) -> None:
    """Register a liveness probe endpoint."""
    @self.get(livez_url, include_in_schema=False)
    async def livez(request: Request) -> dict[str, str]:
        return {"status": "alive"}
    _ = livez

def _setup_readyz_route(self, readyz_url: str) -> None:
    """Register a readiness probe endpoint."""
    checks_ref = self._readiness_checks

    @self.get(readyz_url, include_in_schema=False)
    async def readyz(request: Request) -> Response:
        results: dict[str, dict[str, Any]] = {}
        all_ok = True
        for name, check_func in checks_ref.items():
            try:
                ok, detail = await check_func()
                results[name] = {"ok": ok, "detail": detail}
                if not ok:
                    all_ok = False
            except Exception as exc:
                results[name] = {"ok": False, "detail": str(exc)}
                all_ok = False

        status = "ready" if all_ok else "not_ready"
        body = encode_response({"status": status, "checks": results})
        return Response(
            content=body,
            status_code=200 if all_ok else 503,
            content_type="application/json",
        )
    _ = readyz
```

Note: Add `from hawkapi.serialization.encoder import encode_response` — already imported at top of `app.py`.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_health_probes.py -v`
Expected: PASS (6 tests)

**Step 5: Run full suite + commit**

```bash
uv run pytest tests/ -x -q
git add src/hawkapi/app.py tests/unit/test_health_probes.py
git commit -m "feat: add /readyz and /livez health probe endpoints"
```

---

### Task 4: Deprecation Headers

**Files:**
- Modify: `src/hawkapi/routing/route.py`
- Modify: `src/hawkapi/routing/router.py`
- Modify: `src/hawkapi/app.py`
- Create: `tests/unit/test_deprecation_headers.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_deprecation_headers.py
"""Tests for deprecation response headers."""

import pytest

from hawkapi import HawkAPI


async def _call_app(app, method, path, headers=None, body=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestDeprecationHeaders:
    @pytest.mark.asyncio
    async def test_deprecated_route_emits_deprecation_header(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True)
        async def old():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/old")
        assert resp["status"] == 200
        assert resp["headers"].get(b"deprecation") == b"true"

    @pytest.mark.asyncio
    async def test_sunset_header_emitted(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True, sunset="Sat, 01 Jun 2026 00:00:00 GMT")
        async def old():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/old")
        assert resp["headers"].get(b"sunset") == b"Sat, 01 Jun 2026 00:00:00 GMT"

    @pytest.mark.asyncio
    async def test_deprecation_link_header(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/old", deprecated=True, deprecation_link="https://docs.example.com/migration")
        async def old():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/old")
        link = resp["headers"].get(b"link")
        assert link is not None
        assert b"https://docs.example.com/migration" in link
        assert b'rel="deprecation"' in link

    @pytest.mark.asyncio
    async def test_non_deprecated_route_no_headers(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/new")
        async def new():
            return {"ok": True}

        resp = await _call_app(app, "GET", "/new")
        assert b"deprecation" not in resp["headers"]
        assert b"sunset" not in resp["headers"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_deprecation_headers.py -v`
Expected: FAIL

**Step 3: Modify Route dataclass**

In `src/hawkapi/routing/route.py`, add two fields after `deprecated`:

```python
sunset: str | None = None
deprecation_link: str | None = None
```

**Step 4: Modify Router to pass new kwargs**

In `src/hawkapi/routing/router.py`, update `add_route` signature to accept `sunset` and `deprecation_link`, and pass them to Route constructor. Also update `_route_decorator` to accept and forward these kwargs.

**Step 5: Modify `_core_handler_inner` in `app.py`**

After the HEAD check block (around line 601-605), before `await response(scope, receive, send)`, inject deprecation headers:

```python
# Inject deprecation headers if route is deprecated
if route.deprecated:
    dep_headers: dict[str, str] = {"deprecation": "true"}
    if route.sunset:
        dep_headers["sunset"] = route.sunset
    if route.deprecation_link:
        dep_headers["link"] = f'<{route.deprecation_link}>; rel="deprecation"'
    if hasattr(response, "_headers"):
        response._headers.update(dep_headers)
```

**Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_deprecation_headers.py -v`
Expected: PASS (4 tests)

**Step 7: Run full suite + commit**

```bash
uv run pytest tests/ -x -q
git add src/hawkapi/routing/route.py src/hawkapi/routing/router.py src/hawkapi/app.py tests/unit/test_deprecation_headers.py
git commit -m "feat: add Deprecation, Sunset, and Link headers for deprecated routes"
```

---

### Task 5: CircuitBreakerMiddleware

**Files:**
- Create: `src/hawkapi/middleware/circuit_breaker.py`
- Create: `tests/unit/test_circuit_breaker.py`
- Modify: `src/hawkapi/__init__.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_circuit_breaker.py
"""Tests for circuit breaker middleware."""

import time

import pytest

from hawkapi.middleware.circuit_breaker import CircuitBreakerMiddleware


async def _make_app(status=200, raise_exc=False):
    async def app(scope, receive, send):
        if raise_exc:
            raise RuntimeError("boom")
        await send({"type": "http.response.start", "status": status, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return app


async def _call(middleware, path="/test"):
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    try:
        await middleware(scope, receive, send)
    except RuntimeError:
        pass
    return sent[0]["status"] if sent else None


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_passes_through_normally(self):
        inner = await _make_app(200)
        cb = CircuitBreakerMiddleware(inner, failure_threshold=3, recovery_timeout=1.0)
        status = await _call(cb)
        assert status == 200

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        inner = await _make_app(500)
        cb = CircuitBreakerMiddleware(inner, failure_threshold=3, recovery_timeout=60.0)

        for _ in range(3):
            await _call(cb)

        # Now circuit should be open — returns 503 without calling inner
        calls = []
        original_app = cb.app

        async def tracking_app(scope, receive, send):
            calls.append(True)
            await original_app(scope, receive, send)

        cb.app = tracking_app
        status = await _call(cb)
        assert status == 503
        assert len(calls) == 0  # Inner app was NOT called

    @pytest.mark.asyncio
    async def test_exception_counts_as_failure(self):
        inner = await _make_app(raise_exc=True)
        cb = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=60.0)

        for _ in range(2):
            await _call(cb)

        # Circuit open now — next call returns 503
        cb.app = await _make_app(200)
        status = await _call(cb)
        assert status == 503

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        called = []

        async def inner(scope, receive, send):
            called.append(True)

        cb = CircuitBreakerMiddleware(inner, failure_threshold=3)
        await cb({"type": "websocket"}, None, None)
        assert called == [True]

    @pytest.mark.asyncio
    async def test_half_open_allows_probe(self):
        inner = await _make_app(500)
        cb = CircuitBreakerMiddleware(inner, failure_threshold=2, recovery_timeout=0.01)

        # Trip the breaker
        for _ in range(2):
            await _call(cb)

        # Wait for recovery timeout
        import asyncio

        await asyncio.sleep(0.05)

        # Now in HALF_OPEN — should allow one probe
        cb.app = await _make_app(200)
        status = await _call(cb)
        assert status == 200
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_circuit_breaker.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/middleware/circuit_breaker.py
"""Circuit breaker middleware — prevent cascading failures."""

from __future__ import annotations

import enum
import time
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.serialization.encoder import encode_response


class _State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class _CircuitState:
    __slots__ = ("state", "failure_count", "opened_at", "half_open_calls")

    def __init__(self) -> None:
        self.state = _State.CLOSED
        self.failure_count = 0
        self.opened_at = 0.0
        self.half_open_calls = 0


class CircuitBreakerMiddleware(Middleware):
    """Three-state circuit breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED.

    Tracks failures per path. When failure_threshold consecutive failures occur,
    opens the circuit and returns 503 immediately. After recovery_timeout seconds,
    allows a probe request (HALF_OPEN). If probe succeeds, closes. If fails, re-opens.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
    ) -> None:
        super().__init__(app)
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._circuits: dict[str, _CircuitState] = {}

    def _get_circuit(self, path: str) -> _CircuitState:
        circuit = self._circuits.get(path)
        if circuit is None:
            circuit = _CircuitState()
            self._circuits[path] = circuit
        return circuit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        circuit = self._get_circuit(path)

        # Check if circuit is OPEN
        if circuit.state == _State.OPEN:
            if time.monotonic() - circuit.opened_at >= self._recovery_timeout:
                circuit.state = _State.HALF_OPEN
                circuit.half_open_calls = 0
            else:
                await self._send_503(scope, receive, send)
                return

        # Check if HALF_OPEN and too many probes already
        if circuit.state == _State.HALF_OPEN:
            if circuit.half_open_calls >= self._half_open_max_calls:
                await self._send_503(scope, receive, send)
                return
            circuit.half_open_calls += 1

        # Try the request
        status_code = 500

        async def capture_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_send)
        except Exception:
            self._record_failure(circuit)
            raise

        if status_code >= 500:
            self._record_failure(circuit)
        else:
            self._record_success(circuit)

    def _record_failure(self, circuit: _CircuitState) -> None:
        circuit.failure_count += 1
        if circuit.failure_count >= self._failure_threshold:
            circuit.state = _State.OPEN
            circuit.opened_at = time.monotonic()

    def _record_success(self, circuit: _CircuitState) -> None:
        circuit.state = _State.CLOSED
        circuit.failure_count = 0

    async def _send_503(self, scope: Scope, receive: Receive, send: Send) -> None:
        body = encode_response(
            {
                "type": "https://hawkapi.ashimov.com/errors/circuit-open",
                "title": "Service Unavailable",
                "status": 503,
                "detail": "Circuit breaker is open",
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
```

**Step 4: Run tests, add lazy import, full suite, commit**

Run: `uv run pytest tests/unit/test_circuit_breaker.py -v`
Expected: PASS (5 tests)

Add to `__init__.py`: `CircuitBreakerMiddleware` in lazy imports, TYPE_CHECKING, and `__all__`.

```bash
uv run pytest tests/ -x -q
git add src/hawkapi/middleware/circuit_breaker.py tests/unit/test_circuit_breaker.py src/hawkapi/__init__.py
git commit -m "feat: add CircuitBreakerMiddleware with three-state pattern"
```

---

## Wave 2: Contract & Quality Pipeline

### Task 6: OpenAPI Linter + `hawk check`

**Files:**
- Create: `src/hawkapi/openapi/linter.py`
- Modify: `src/hawkapi/cli.py`
- Create: `tests/unit/test_openapi_linter.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_openapi_linter.py
"""Tests for OpenAPI linter."""

import pytest

from hawkapi.openapi.linter import LintIssue, Severity, lint


class TestLinter:
    def test_missing_operation_id(self):
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            }
        }
        issues = lint(spec)
        assert any(
            i.rule == "operation-id-required" for i in issues
        )

    def test_operation_id_present_no_issue(self):
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "summary": "List users",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            }
        }
        issues = lint(spec)
        assert not any(i.rule == "operation-id-required" for i in issues)

    def test_missing_summary(self):
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            }
        }
        issues = lint(spec)
        assert any(i.rule == "operation-summary-required" for i in issues)

    def test_missing_response_description(self):
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "summary": "List users",
                        "responses": {"200": {}},
                    }
                }
            }
        }
        issues = lint(spec)
        assert any(i.rule == "response-description-required" for i in issues)

    def test_clean_spec_no_issues(self):
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "listUsers",
                        "summary": "List users",
                        "responses": {"200": {"description": "Success"}},
                    }
                }
            }
        }
        issues = lint(spec)
        assert len(issues) == 0

    def test_empty_spec_no_issues(self):
        spec = {"paths": {}}
        issues = lint(spec)
        assert len(issues) == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_openapi_linter.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/openapi/linter.py
"""OpenAPI specification linter."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class LintIssue:
    """A single linting issue."""

    rule: str
    severity: Severity
    path: str
    method: str
    message: str


LintRule = Any  # Callable[[dict, str, str, dict], list[LintIssue]]


def _check_operation_id(
    spec: dict[str, Any], path: str, method: str, operation: dict[str, Any]
) -> list[LintIssue]:
    if "operationId" not in operation:
        return [
            LintIssue(
                rule="operation-id-required",
                severity=Severity.WARNING,
                path=path,
                method=method,
                message=f"{method.upper()} {path} is missing operationId",
            )
        ]
    return []


def _check_summary(
    spec: dict[str, Any], path: str, method: str, operation: dict[str, Any]
) -> list[LintIssue]:
    if "summary" not in operation and "description" not in operation:
        return [
            LintIssue(
                rule="operation-summary-required",
                severity=Severity.WARNING,
                path=path,
                method=method,
                message=f"{method.upper()} {path} is missing summary or description",
            )
        ]
    return []


def _check_response_descriptions(
    spec: dict[str, Any], path: str, method: str, operation: dict[str, Any]
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for status, response in operation.get("responses", {}).items():
        if not response.get("description"):
            issues.append(
                LintIssue(
                    rule="response-description-required",
                    severity=Severity.WARNING,
                    path=path,
                    method=method,
                    message=f"{method.upper()} {path} response {status} is missing description",
                )
            )
    return issues


_DEFAULT_RULES: list[LintRule] = [
    _check_operation_id,
    _check_summary,
    _check_response_descriptions,
]

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def lint(
    spec: dict[str, Any],
    *,
    rules: list[LintRule] | None = None,
) -> list[LintIssue]:
    """Lint an OpenAPI specification and return issues found."""
    active_rules = rules if rules is not None else _DEFAULT_RULES
    issues: list[LintIssue] = []

    for path, methods in spec.get("paths", {}).items():
        for method, operation in methods.items():
            if method.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue
            for rule in active_rules:
                issues.extend(rule(spec, path, method, operation))

    return issues


def format_lint_report(issues: list[LintIssue]) -> str:
    """Format lint issues into a human-readable report."""
    if not issues:
        return "No issues found."

    lines: list[str] = []
    for issue in issues:
        severity = issue.severity.value.upper()
        lines.append(f"  [{severity}] {issue.rule}: {issue.message}")
    return f"Found {len(issues)} issue(s):\n" + "\n".join(lines)
```

**Step 4: Add `check` subcommand to CLI**

In `src/hawkapi/cli.py`, add after the diff subparser:

```python
# `hawkapi check` subcommand
check_parser = subparsers.add_parser("check", help="Lint OpenAPI specification")
check_parser.add_argument("app", help="App reference (module:attr, e.g. myapp.main:app)")
```

In `main()`, add:

```python
elif args.command == "check":
    sys.exit(_run_check(args))
```

Add the handler:

```python
def _run_check(args: argparse.Namespace) -> int:
    """Lint the app's OpenAPI spec."""
    from hawkapi.openapi.linter import format_lint_report, lint

    module_path, attr = _parse_ref(args.app)
    mod = importlib.import_module(module_path)
    spec = _load_app_spec(mod, attr)
    issues = lint(spec)
    print(format_lint_report(issues))
    return 1 if issues else 0
```

**Step 5: Run tests, full suite, commit**

```bash
uv run pytest tests/unit/test_openapi_linter.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/openapi/linter.py src/hawkapi/cli.py tests/unit/test_openapi_linter.py
git commit -m "feat: add OpenAPI linter and 'hawkapi check' CLI command"
```

---

### Task 7: Changelog Generator

**Files:**
- Create: `src/hawkapi/openapi/changelog.py`
- Modify: `src/hawkapi/cli.py`
- Create: `tests/unit/test_changelog.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_changelog.py
"""Tests for OpenAPI changelog generator."""

from hawkapi.openapi.breaking_changes import Change, ChangeType, Severity
from hawkapi.openapi.changelog import generate_changelog


class TestChangelog:
    def test_empty_changes(self):
        md = generate_changelog([])
        assert "No changes" in md

    def test_breaking_change_listed(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.BREAKING,
                path="/users",
                method="get",
                description="Endpoint removed",
            )
        ]
        md = generate_changelog(changes)
        assert "Breaking" in md
        assert "/users" in md

    def test_grouping(self):
        changes = [
            Change(
                type=ChangeType.PATH_REMOVED,
                severity=Severity.BREAKING,
                path="/a",
                method="get",
                description="removed",
            ),
            Change(
                type=ChangeType.PARAMETER_REMOVED,
                severity=Severity.WARNING,
                path="/b",
                method="post",
                description="param removed",
            ),
        ]
        md = generate_changelog(changes)
        assert "Breaking" in md
        assert "Changed" in md
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_changelog.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/openapi/changelog.py
"""Changelog generator from OpenAPI diff."""

from __future__ import annotations

from hawkapi.openapi.breaking_changes import Change, Severity


def generate_changelog(changes: list[Change], *, title: str = "API Changelog") -> str:
    """Generate a Markdown changelog from a list of API changes."""
    if not changes:
        return f"# {title}\n\nNo changes detected.\n"

    breaking = [c for c in changes if c.severity == Severity.BREAKING]
    warnings = [c for c in changes if c.severity == Severity.WARNING]
    info = [c for c in changes if c.severity == Severity.INFO]

    lines: list[str] = [f"# {title}\n"]

    if breaking:
        lines.append("## Breaking\n")
        for c in breaking:
            lines.append(f"- **{c.method.upper()} {c.path}**: {c.description}")
        lines.append("")

    if warnings:
        lines.append("## Changed\n")
        for c in warnings:
            lines.append(f"- **{c.method.upper()} {c.path}**: {c.description}")
        lines.append("")

    if info:
        lines.append("## Info\n")
        for c in info:
            lines.append(f"- **{c.method.upper()} {c.path}**: {c.description}")
        lines.append("")

    return "\n".join(lines)
```

**Step 4: Add `changelog` subcommand to CLI**

In `src/hawkapi/cli.py`, add subparser and handler:

```python
# `hawkapi changelog` subcommand
changelog_parser = subparsers.add_parser("changelog", help="Generate changelog from API diff")
changelog_parser.add_argument("old", help="Old app reference (module:attr)")
changelog_parser.add_argument("new", help="New app reference (module:attr)")
```

Handler:

```python
elif args.command == "changelog":
    _run_changelog(args)
```

```python
def _run_changelog(args: argparse.Namespace) -> None:
    """Generate changelog from two app versions."""
    from hawkapi.openapi.changelog import generate_changelog

    old_module_path, old_attr = _parse_ref(args.old)
    new_module_path, new_attr = _parse_ref(args.new)

    old_mod = importlib.import_module(old_module_path)
    new_mod = importlib.import_module(new_module_path)

    old_spec = _load_app_spec(old_mod, old_attr)
    new_spec = _load_app_spec(new_mod, new_attr)

    changes = _diff_specs(old_spec, new_spec)
    print(generate_changelog(changes))
```

**Step 5: Run tests, full suite, commit**

```bash
uv run pytest tests/unit/test_changelog.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/openapi/changelog.py src/hawkapi/cli.py tests/unit/test_changelog.py
git commit -m "feat: add changelog generator and 'hawkapi changelog' CLI command"
```

---

### Task 8: Contract Smoke Tests

**Files:**
- Create: `src/hawkapi/testing/contract.py`
- Create: `tests/unit/test_contract_tests.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_contract_tests.py
"""Tests for contract smoke test generator."""

import pytest

from hawkapi import HawkAPI
from hawkapi.testing.contract import generate_contract_tests


class TestContractTestGenerator:
    def test_generates_tests_for_each_endpoint(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/users")
        async def list_users():
            return [{"id": 1}]

        @app.post("/users")
        async def create_user():
            return {"id": 1}

        tests = generate_contract_tests(app)
        assert len(tests) >= 2

    def test_generated_test_returns_expected_status(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        tests = generate_contract_tests(app)
        # Each test is a (name, method, path, expected_status) tuple
        ping_tests = [t for t in tests if t.path == "/ping"]
        assert len(ping_tests) == 1
        assert ping_tests[0].method == "GET"
        assert ping_tests[0].expected_status == 200

    def test_custom_status_code(self):
        app = HawkAPI(openapi_url=None)

        @app.post("/items", status_code=201)
        async def create():
            return {"id": 1}

        tests = generate_contract_tests(app)
        create_tests = [t for t in tests if t.path == "/items"]
        assert create_tests[0].expected_status == 201
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_contract_tests.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/testing/contract.py
"""Contract smoke test generator from app routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContractTest:
    """A single contract test case."""

    name: str
    method: str
    path: str
    expected_status: int


def generate_contract_tests(app: Any) -> list[ContractTest]:
    """Generate contract test cases from an app's routes.

    Returns a list of ContractTest describing the expected behavior
    for each registered route.
    """
    tests: list[ContractTest] = []

    for route in app.routes:
        if not route.include_in_schema:
            continue
        for method in sorted(route.methods):
            # Skip path-param routes (would need sample values)
            if "{" in route.path:
                continue
            name = f"{method} {route.path} -> {route.status_code}"
            tests.append(
                ContractTest(
                    name=name,
                    method=method,
                    path=route.path,
                    expected_status=route.status_code,
                )
            )

    return tests
```

**Step 4: Run tests, full suite, commit**

```bash
uv run pytest tests/unit/test_contract_tests.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/testing/contract.py tests/unit/test_contract_tests.py
git commit -m "feat: add contract smoke test generator"
```

---

### Task 9: Client SDK Generation Templates

**Files:**
- Create: `templates/sdk-generator/typescript.md`
- Create: `templates/sdk-generator/python.md`

**Step 1: Write the TypeScript SDK template doc**

```markdown
# TypeScript Client SDK Generation

## Using openapi-generator-cli

```bash
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g typescript-fetch \
  -o ./sdk/typescript \
  --additional-properties=supportsES6=true,typescriptThreePlus=true
```

## Using openapi-typescript

```bash
npx openapi-typescript http://localhost:8000/openapi.json -o ./sdk/types.ts
```

## Manual fetch wrapper

```typescript
// api-client.ts
const BASE_URL = process.env.API_URL || "http://localhost:8000";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}
```
```

**Step 2: Write the Python SDK template doc**

```markdown
# Python Client SDK Generation

## Using openapi-generator-cli

```bash
npx @openapitools/openapi-generator-cli generate \
  -i http://localhost:8000/openapi.json \
  -g python \
  -o ./sdk/python \
  --additional-properties=packageName=myapp_client
```

## Using httpx + msgspec

```python
# client.py
import httpx
import msgspec

class APIClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self._client = httpx.AsyncClient(base_url=base_url)

    async def request(self, method: str, path: str, **kwargs):
        resp = await self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return msgspec.json.decode(resp.content)

    async def close(self):
        await self._client.aclose()
```
```

**Step 3: Commit**

```bash
git add templates/sdk-generator/
git commit -m "docs: add client SDK generation templates for TypeScript and Python"
```

---

## Wave 3: DX & Introspection

### Task 10: `hawk new` Project Scaffold

**Files:**
- Create: `src/hawkapi/_scaffold/__init__.py`
- Create: `src/hawkapi/_scaffold/templates.py`
- Modify: `src/hawkapi/cli.py`
- Create: `tests/unit/test_scaffold.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_scaffold.py
"""Tests for project scaffold generator."""

import os
import tempfile

from hawkapi._scaffold.templates import generate_project


class TestScaffold:
    def test_generates_main_py(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "myproject")
            generate_project(project_dir, name="myproject")
            assert os.path.isfile(os.path.join(project_dir, "main.py"))

    def test_generates_pyproject_toml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "myproject")
            generate_project(project_dir, name="myproject")
            content = open(os.path.join(project_dir, "pyproject.toml")).read()
            assert "hawkapi" in content
            assert "myproject" in content

    def test_generates_dockerfile(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "myproject")
            generate_project(project_dir, name="myproject", docker=True)
            assert os.path.isfile(os.path.join(project_dir, "Dockerfile"))

    def test_no_dockerfile_when_not_requested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "myproject")
            generate_project(project_dir, name="myproject", docker=False)
            assert not os.path.isfile(os.path.join(project_dir, "Dockerfile"))
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_scaffold.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/_scaffold/__init__.py
```

```python
# src/hawkapi/_scaffold/templates.py
"""Project scaffold templates."""

from __future__ import annotations

import os

MAIN_PY = '''\
"""Application entry point."""

from hawkapi import HawkAPI

app = HawkAPI(title="{name}")


@app.get("/")
async def root():
    return {{"message": "Welcome to {name}!"}}


@app.get("/health")
async def health():
    return {{"status": "ok"}}
'''

PYPROJECT_TOML = '''\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["hawkapi>=0.1.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "ruff>=0.8"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
'''

DOCKERFILE = '''\
FROM python:3.12-slim AS base

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000
CMD ["uv", "run", "hawkapi", "dev", "main:app", "--host", "0.0.0.0"]
'''

GITIGNORE = '''\
__pycache__/
*.pyc
.venv/
dist/
.ruff_cache/
'''


def generate_project(
    project_dir: str,
    *,
    name: str,
    docker: bool = False,
) -> None:
    """Generate a HawkAPI project scaffold."""
    os.makedirs(project_dir, exist_ok=True)

    _write(project_dir, "main.py", MAIN_PY.format(name=name))
    _write(project_dir, "pyproject.toml", PYPROJECT_TOML.format(name=name))
    _write(project_dir, ".gitignore", GITIGNORE)

    if docker:
        _write(project_dir, "Dockerfile", DOCKERFILE)


def _write(base: str, filename: str, content: str) -> None:
    path = os.path.join(base, filename)
    with open(path, "w") as f:
        f.write(content)
```

**Step 4: Add `new` subcommand to CLI**

In `src/hawkapi/cli.py`:

```python
# `hawkapi new` subcommand
new_parser = subparsers.add_parser("new", help="Create a new HawkAPI project")
new_parser.add_argument("name", help="Project name")
new_parser.add_argument("--docker", action="store_true", help="Include Dockerfile")
```

Handler:

```python
elif args.command == "new":
    _run_new(args)
```

```python
def _run_new(args: argparse.Namespace) -> None:
    """Scaffold a new project."""
    from hawkapi._scaffold.templates import generate_project

    project_dir = os.path.join(os.getcwd(), args.name)
    if os.path.exists(project_dir):
        print(f"Error: directory '{args.name}' already exists", file=sys.stderr)
        sys.exit(1)
    generate_project(project_dir, name=args.name, docker=args.docker)
    print(f"Created project '{args.name}' in ./{args.name}/")
    print(f"  cd {args.name} && uv sync && hawkapi dev main:app")
```

Add `import os` at top of cli.py if not present.

**Step 5: Run tests, full suite, commit**

```bash
uv run pytest tests/unit/test_scaffold.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/_scaffold/ src/hawkapi/cli.py tests/unit/test_scaffold.py
git commit -m "feat: add 'hawkapi new' project scaffolding command"
```

---

### Task 11: DI Introspection

**Files:**
- Create: `src/hawkapi/di/introspection.py`
- Modify: `src/hawkapi/di/container.py`
- Create: `tests/unit/test_di_introspection.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_di_introspection.py
"""Tests for DI container introspection."""

from hawkapi.di.container import Container
from hawkapi.di.introspection import container_graph


class Service:
    pass


class Repository:
    pass


class TestDIIntrospection:
    def test_graph_returns_providers(self):
        c = Container()
        c.singleton(Service, factory=Service)
        graph = container_graph(c)
        assert "Service" in graph

    def test_graph_shows_lifecycle(self):
        c = Container()
        c.scoped(Repository, factory=Repository)
        graph = container_graph(c)
        assert graph["Repository"]["lifecycle"] == "scoped"

    def test_empty_container(self):
        c = Container()
        graph = container_graph(c)
        assert graph == {}

    def test_to_mermaid(self):
        from hawkapi.di.introspection import to_mermaid

        c = Container()
        c.singleton(Service, factory=Service)
        c.scoped(Repository, factory=Repository)
        mermaid = to_mermaid(c)
        assert "graph TD" in mermaid
        assert "Service" in mermaid
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_di_introspection.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/di/introspection.py
"""DI container introspection utilities."""

from __future__ import annotations

from typing import Any


def container_graph(container: Any) -> dict[str, dict[str, Any]]:
    """Return a dict describing all registered providers.

    Returns:
        {
            "ServiceName": {
                "lifecycle": "singleton" | "scoped" | "transient",
                "factory": "<callable repr>",
                "name": None | "qualifier",
            }
        }
    """
    graph: dict[str, dict[str, Any]] = {}
    for (service_type, name), provider in container._providers.items():
        key = service_type.__name__
        if name:
            key = f"{key}[{name}]"
        graph[key] = {
            "lifecycle": provider.lifecycle.value,
            "factory": repr(provider.factory),
            "name": name,
        }
    return graph


def to_mermaid(container: Any) -> str:
    """Generate a Mermaid diagram of the DI container."""
    graph = container_graph(container)
    lines: list[str] = ["graph TD"]
    for service, info in graph.items():
        lifecycle = info["lifecycle"]
        shape_open, shape_close = {
            "singleton": ("([", "])"),
            "scoped": ("[[", "]]"),
            "transient": ("((", "))"),
        }.get(lifecycle, ("[", "]"))
        lines.append(f"    {service}{shape_open}{service} ({lifecycle}){shape_close}")
    return "\n".join(lines)
```

**Step 4: Run tests, full suite, commit**

```bash
uv run pytest tests/unit/test_di_introspection.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/di/introspection.py tests/unit/test_di_introspection.py
git commit -m "feat: add DI container introspection and Mermaid diagram generation"
```

---

### Task 12: Debug Endpoints Middleware

**Files:**
- Create: `src/hawkapi/middleware/debug.py`
- Create: `tests/unit/test_debug_middleware.py`
- Modify: `src/hawkapi/__init__.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_debug_middleware.py
"""Tests for debug endpoints middleware."""

import msgspec
import pytest

from hawkapi import HawkAPI
from hawkapi.middleware.debug import DebugMiddleware


async def _call_app(app, method, path, headers=None, body=b""):
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "root_path": "",
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        sent.append(message)

    await app(scope, receive, send)
    return {
        "status": sent[0]["status"],
        "headers": dict(sent[0].get("headers", [])),
        "body": sent[1].get("body", b"") if len(sent) > 1 else b"",
    }


class TestDebugMiddleware:
    @pytest.mark.asyncio
    async def test_debug_routes_endpoint(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(DebugMiddleware)

        @app.get("/users")
        async def list_users():
            return []

        resp = await _call_app(app, "GET", "/_debug/routes")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        paths = [r["path"] for r in body]
        assert "/users" in paths

    @pytest.mark.asyncio
    async def test_debug_stats_endpoint(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(DebugMiddleware)

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Make a request to generate stats
        await _call_app(app, "GET", "/test")

        resp = await _call_app(app, "GET", "/_debug/stats")
        assert resp["status"] == 200
        body = msgspec.json.decode(resp["body"])
        assert isinstance(body, dict)

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        called = []

        async def inner(scope, receive, send):
            called.append(True)

        middleware = DebugMiddleware(inner)
        await middleware({"type": "websocket"}, None, None)
        assert called == [True]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_debug_middleware.py -v`
Expected: FAIL

**Step 3: Write the implementation**

```python
# src/hawkapi/middleware/debug.py
"""Debug endpoints middleware — exposes /_debug/* for development."""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import msgspec

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class DebugMiddleware(Middleware):
    """Expose debug endpoints for route listing and request stats.

    Endpoints:
        - /_debug/routes — list all registered routes
        - /_debug/stats — per-path request count and avg latency
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        prefix: str = "/_debug",
    ) -> None:
        super().__init__(app)
        self._prefix = prefix
        self._stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"count": 0, "total_time": 0.0, "errors": 0}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]

        if path == f"{self._prefix}/routes":
            await self._serve_routes(scope, receive, send)
            return

        if path == f"{self._prefix}/stats":
            await self._serve_stats(scope, receive, send)
            return

        # Track stats for non-debug requests
        start = time.monotonic()
        status_code = 500

        async def stats_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, stats_send)
        finally:
            duration = time.monotonic() - start
            entry = self._stats[path]
            entry["count"] += 1
            entry["total_time"] += duration
            if status_code >= 500:
                entry["errors"] += 1

    async def _serve_routes(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Walk the app to find routes
        app = self.app
        routes: list[dict[str, Any]] = []

        # Try to access .routes from the inner app (HawkAPI stores routes)
        inner = app
        while hasattr(inner, "app"):
            inner = inner.app
        if hasattr(inner, "routes"):
            for route in inner.routes:
                routes.append(
                    {
                        "path": route.path,
                        "methods": sorted(route.methods),
                        "name": route.name,
                        "deprecated": route.deprecated,
                    }
                )

        body = msgspec.json.encode(routes)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    async def _serve_stats(self, scope: Scope, receive: Receive, send: Send) -> None:
        stats: dict[str, dict[str, Any]] = {}
        for path, data in self._stats.items():
            count = data["count"]
            stats[path] = {
                "count": count,
                "avg_latency_ms": round((data["total_time"] / count) * 1000, 2)
                if count > 0
                else 0,
                "errors": data["errors"],
            }

        body = msgspec.json.encode(stats)
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
```

**Step 4: Add lazy import, run tests, commit**

Add to `__init__.py`: `DebugMiddleware` in lazy imports, TYPE_CHECKING, `__all__`.

```bash
uv run pytest tests/unit/test_debug_middleware.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/middleware/debug.py tests/unit/test_debug_middleware.py src/hawkapi/__init__.py
git commit -m "feat: add DebugMiddleware with /_debug/routes and /_debug/stats"
```

---

### Task 13: Plugin API

**Files:**
- Create: `src/hawkapi/plugins.py`
- Modify: `src/hawkapi/app.py`
- Create: `tests/unit/test_plugin_api.py`

**Step 1: Write the failing tests**

```python
# tests/unit/test_plugin_api.py
"""Tests for the plugin API."""

import pytest

from hawkapi import HawkAPI
from hawkapi.plugins import Plugin


class TestPluginAPI:
    def test_plugin_on_route_registered(self):
        registered = []

        class MyPlugin(Plugin):
            def on_route_registered(self, route):
                registered.append(route.path)
                return route

        app = HawkAPI(openapi_url=None)
        app.add_plugin(MyPlugin())

        @app.get("/test")
        async def handler():
            return {"ok": True}

        assert "/test" in registered

    def test_plugin_on_schema_generated(self):
        class EnrichPlugin(Plugin):
            def on_schema_generated(self, spec):
                spec["x-custom"] = True
                return spec

        app = HawkAPI()
        app.add_plugin(EnrichPlugin())

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        spec = app.openapi()
        assert spec.get("x-custom") is True

    def test_multiple_plugins(self):
        calls = []

        class PluginA(Plugin):
            def on_route_registered(self, route):
                calls.append("A")
                return route

        class PluginB(Plugin):
            def on_route_registered(self, route):
                calls.append("B")
                return route

        app = HawkAPI(openapi_url=None)
        app.add_plugin(PluginA())
        app.add_plugin(PluginB())

        @app.get("/test")
        async def handler():
            return {"ok": True}

        assert calls == ["A", "B"]

    def test_plugin_default_methods_are_noop(self):
        """A plugin with no overrides should not break anything."""
        app = HawkAPI(openapi_url=None)
        app.add_plugin(Plugin())

        @app.get("/test")
        async def handler():
            return {"ok": True}

        # Should not raise
        spec = app.openapi()
        assert "/test" in spec["paths"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_plugin_api.py -v`
Expected: FAIL

**Step 3: Write the Plugin protocol**

```python
# src/hawkapi/plugins.py
"""Plugin API for HawkAPI."""

from __future__ import annotations

from typing import Any


class Plugin:
    """Base plugin class. Override hooks to customize behavior.

    Hooks:
        on_route_registered(route) -> route — called when a route is added
        on_schema_generated(spec) -> spec — called when OpenAPI schema is generated
    """

    def on_route_registered(self, route: Any) -> Any:
        """Called when a route is registered. Return the (possibly modified) route."""
        return route

    def on_schema_generated(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Called when OpenAPI schema is generated. Return the (possibly enriched) spec."""
        return spec
```

**Step 4: Modify `src/hawkapi/app.py`**

Add `_plugins` list to `__init__`:

```python
self._plugins: list[Any] = []
```

Add `add_plugin` method:

```python
def add_plugin(self, plugin: Any) -> None:
    """Register a plugin."""
    self._plugins.append(plugin)
```

Modify `add_route` to notify plugins:

```python
def add_route(self, path: str, handler: Any, **kwargs: Any) -> Route:
    self._invalidate_openapi_cache()
    route = super().add_route(path, handler, **kwargs)
    for plugin in self._plugins:
        if hasattr(plugin, "on_route_registered"):
            route = plugin.on_route_registered(route)
    return route
```

Modify `openapi()` to call plugin hooks:

```python
def openapi(self, api_version: str | None = None) -> dict[str, Any]:
    from hawkapi.openapi.schema import generate_openapi
    cache_key = api_version or "__all__"
    if cache_key not in self._openapi_cache:
        spec = generate_openapi(
            self._collect_routes(),
            title=self.title,
            version=self.version,
            description=self.description,
            api_version=api_version,
        )
        for plugin in self._plugins:
            if hasattr(plugin, "on_schema_generated"):
                spec = plugin.on_schema_generated(spec)
        self._openapi_cache[cache_key] = spec
    import copy
    return copy.deepcopy(self._openapi_cache[cache_key])
```

**Step 5: Add lazy import, run tests, commit**

Add to `__init__.py`: `Plugin` in lazy imports (module `hawkapi.plugins`), TYPE_CHECKING, `__all__`.

```bash
uv run pytest tests/unit/test_plugin_api.py -v
uv run pytest tests/ -x -q
git add src/hawkapi/plugins.py src/hawkapi/app.py tests/unit/test_plugin_api.py src/hawkapi/__init__.py
git commit -m "feat: add Plugin API with route registration and schema generation hooks"
```

---

## Final Verification

After all 13 tasks:

```bash
uv run pytest tests/ -x -q          # All tests pass
uv run ruff check src/ tests/       # 0 errors
uv run ruff format --check src/ tests/  # 0 issues
uv run pyright src/                  # Only pre-existing errors
```
