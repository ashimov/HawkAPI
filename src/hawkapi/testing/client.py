"""Built-in test client — sync API over async ASGI.

No async/sync split like FastAPI. Works the same way everywhere.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlencode

import msgspec

from hawkapi._types import ASGIApp


class TestResponse:
    """Response returned by TestClient."""

    __slots__ = ("status_code", "body", "_headers_raw", "_json_cache")

    def __init__(
        self,
        status_code: int,
        body: bytes,
        headers: list[tuple[bytes, bytes]],
    ) -> None:
        self.status_code = status_code
        self.body = body
        self._headers_raw = headers
        self._json_cache: Any = None

    @property
    def text(self) -> str:
        """Response body decoded as UTF-8 text."""
        return self.body.decode("utf-8")

    @property
    def headers(self) -> dict[str, str]:
        """Response headers as a string-to-string dictionary."""
        return {k.decode("latin-1"): v.decode("latin-1") for k, v in self._headers_raw}

    def json(self) -> Any:
        """Deserialize the response body from JSON (cached)."""
        if self._json_cache is None:
            self._json_cache = msgspec.json.decode(self.body)
        return self._json_cache

    def __repr__(self) -> str:
        return f"<TestResponse [{self.status_code}]>"


class TestClient:
    """Synchronous test client for HawkAPI apps.

    Usage:
        client = TestClient(app)
        response = client.get("/users")
        assert response.status_code == 200
        assert response.json() == [...]
    """

    def __init__(self, app: ASGIApp, base_url: str = "http://testserver") -> None:
        self.app = app
        self.base_url = base_url
        self._default_headers: dict[str, str] = {}

    def _get_event_loop(self) -> asyncio.AbstractEventLoop:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an async context — create a new loop in a thread
            raise RuntimeError(
                "TestClient cannot be used inside an async context. Use the async methods directly."
            )

        loop = asyncio.new_event_loop()
        return loop

    def get(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a GET request."""
        return self._request("GET", path, headers=headers, params=params)

    def post(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a POST request with optional JSON or raw body."""
        return self._request("POST", path, json=json, body=body, headers=headers, params=params)

    def put(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a PUT request with optional JSON or raw body."""
        return self._request("PUT", path, json=json, body=body, headers=headers, params=params)

    def patch(
        self,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a PATCH request with optional JSON or raw body."""
        return self._request("PATCH", path, json=json, body=body, headers=headers, params=params)

    def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a DELETE request."""
        return self._request("DELETE", path, headers=headers, params=params)

    def head(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send a HEAD request."""
        return self._request("HEAD", path, headers=headers, params=params)

    def options(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Send an OPTIONS request."""
        return self._request("OPTIONS", path, headers=headers, params=params)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Execute a request synchronously."""
        loop = self._get_event_loop()
        try:
            return loop.run_until_complete(
                self._async_request(
                    method,
                    path,
                    json=json,
                    body=body,
                    headers=headers,
                    params=params,
                )
            )
        finally:
            loop.close()

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> TestResponse:
        """Execute a request asynchronously."""
        # Build request body
        request_body = b""
        merged_headers = {**self._default_headers, **(headers or {})}

        if json is not None:
            request_body = msgspec.json.encode(json)
            merged_headers.setdefault("content-type", "application/json")
        elif body is not None:
            request_body = body

        # Build query string
        query_string = b""
        if params:
            query_string = urlencode(params).encode("utf-8")
        elif "?" in path:
            path, _, qs = path.partition("?")
            query_string = qs.encode("utf-8")

        # Build ASGI scope
        raw_headers = [
            (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in merged_headers.items()
        ]

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "path": path,
            "query_string": query_string,
            "root_path": "",
            "scheme": "http",
            "server": ("testserver", 80),
            "headers": raw_headers,
        }

        # Capture response
        response_started = False
        status_code = 0
        response_headers: list[tuple[bytes, bytes]] = []
        body_parts: list[bytes] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": request_body, "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            nonlocal response_started, status_code, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        await self.app(scope, receive, send)

        return TestResponse(
            status_code=status_code,
            body=b"".join(body_parts),
            headers=response_headers,
        )

    # Async versions for use in async tests
    async def async_get(self, path: str, **kwargs: Any) -> TestResponse:
        """Send an async GET request (for use in async test functions)."""
        return await self._async_request("GET", path, **kwargs)

    async def async_post(self, path: str, **kwargs: Any) -> TestResponse:
        """Send an async POST request (for use in async test functions)."""
        return await self._async_request("POST", path, **kwargs)

    async def async_put(self, path: str, **kwargs: Any) -> TestResponse:
        """Send an async PUT request (for use in async test functions)."""
        return await self._async_request("PUT", path, **kwargs)

    async def async_patch(self, path: str, **kwargs: Any) -> TestResponse:
        """Send an async PATCH request (for use in async test functions)."""
        return await self._async_request("PATCH", path, **kwargs)

    async def async_delete(self, path: str, **kwargs: Any) -> TestResponse:
        """Send an async DELETE request (for use in async test functions)."""
        return await self._async_request("DELETE", path, **kwargs)
