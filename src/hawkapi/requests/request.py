"""Request object with lazy parsing and __slots__ optimization."""

from __future__ import annotations

from typing import Any

import msgspec

from hawkapi._types import UNSET, Receive, Scope
from hawkapi.requests.headers import Headers
from hawkapi.requests.query_params import QueryParams
from hawkapi.requests.state import State


class RequestEntityTooLarge(Exception):
    """Raised when the request body exceeds the maximum allowed size."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        super().__init__(f"Request body exceeds maximum size of {max_size} bytes")


# Default: 10 MB
DEFAULT_MAX_BODY_SIZE = 10 * 1024 * 1024


async def read_body(receive: Receive, max_size: int = DEFAULT_MAX_BODY_SIZE) -> bytes:
    """Read the full request body from ASGI receive with size limit."""
    body = bytearray()
    while True:
        message = await receive()
        chunk = message.get("body", b"")
        if chunk:
            if len(body) + len(chunk) > max_size:
                raise RequestEntityTooLarge(max_size)
            body.extend(chunk)
        if not message.get("more_body", False):
            break
    return bytes(body)


class Request:
    """HTTP request wrapper with lazy parsing for maximum performance."""

    __slots__ = (
        "_scope",
        "_receive",
        "_body",
        "_json",
        "_form",
        "_query_params",
        "_headers",
        "_cookies",
        "_path_params",
        "_max_body_size",
        "state",
    )

    def __init__(
        self,
        scope: Scope,
        receive: Receive,
        path_params: dict[str, object] | None = None,
        max_body_size: int = DEFAULT_MAX_BODY_SIZE,
    ) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes | Any = UNSET
        self._json: Any = UNSET
        self._form: Any = UNSET
        self._query_params: QueryParams | Any = UNSET
        self._headers: Headers | Any = UNSET
        self._cookies: dict[str, str] | Any = UNSET
        self._path_params = path_params or {}
        self._max_body_size = max_body_size
        self.state = State()

    @property
    def scope(self) -> Scope:
        """The raw ASGI scope."""
        return self._scope

    @property
    def method(self) -> str:
        """The HTTP method (GET, POST, etc.)."""
        return self._scope["method"]

    @property
    def path(self) -> str:
        """The request path."""
        return self._scope["path"]

    @property
    def query_string(self) -> bytes:
        """The raw query string as bytes."""
        return self._scope.get("query_string", b"")

    @property
    def headers(self) -> Headers:
        """Parsed request headers (lazily cached)."""
        if self._headers is UNSET:
            self._headers = Headers(self._scope.get("headers", []))
        return self._headers

    @property
    def query_params(self) -> QueryParams:
        """Parsed query parameters (lazily cached)."""
        if self._query_params is UNSET:
            self._query_params = QueryParams(self.query_string)
        return self._query_params

    @property
    def path_params(self) -> dict[str, object]:
        """Path parameters extracted from the URL by the router."""
        return self._path_params

    @property
    def content_type(self) -> str | None:
        """The Content-Type header value, or None if absent."""
        return self.headers.get("content-type")

    @property
    def client(self) -> tuple[str, int] | None:
        """Client address as (host, port), or None if unavailable."""
        client = self._scope.get("client")
        if client:
            return (client[0], client[1])
        return None

    @property
    def url(self) -> str:
        """Full request URL reconstructed from scope."""
        scheme = self._scope.get("scheme", "http")
        server = self._scope.get("server")
        path = self._scope.get("path", "/")
        qs = self._scope.get("query_string", b"")

        if server:
            host, port = server
            default_port = 443 if scheme == "https" else 80
            host_str = f"{host}:{port}" if port != default_port else host
        else:
            host_str = self.headers.get("host", "localhost")

        url = f"{scheme}://{host_str}{path}"
        if qs:
            url = f"{url}?{qs.decode('latin-1')}"
        return url

    @property
    def url_scheme(self) -> str:
        """URL scheme (http or https)."""
        return self._scope.get("scheme", "http")

    @property
    def cookies(self) -> dict[str, str]:
        """Parsed cookies from the Cookie header (lazily cached)."""
        if self._cookies is UNSET:
            self._cookies = _parse_cookies(self.headers.get("cookie") or "")
        return self._cookies

    async def body(self) -> bytes:
        """Read and return the full request body (lazily cached)."""
        if self._body is UNSET:
            self._body = await read_body(self._receive, self._max_body_size)
        return self._body

    async def json(self) -> Any:
        """Deserialize the request body from JSON (lazily cached)."""
        if self._json is UNSET:
            raw = await self.body()
            self._json = msgspec.json.decode(raw)
        return self._json

    async def form(self):
        """Parse form data (urlencoded or multipart)."""
        if self._form is UNSET:
            from hawkapi.requests.form_data import parse_multipart, parse_urlencoded

            ct = self.content_type or ""
            raw = await self.body()

            if "multipart/form-data" in ct:
                # Extract boundary
                boundary = ""
                for part in ct.split(";"):
                    part = part.strip()
                    if part.startswith("boundary="):
                        boundary = part[9:].strip('"')
                        break
                self._form = parse_multipart(raw, boundary)
            else:
                self._form = parse_urlencoded(raw)
        return self._form


def _parse_cookies(cookie_header: str) -> dict[str, str]:
    """Parse a Cookie header string into a dict."""
    cookies: dict[str, str] = {}
    if not cookie_header:
        return cookies
    for pair in cookie_header.split(";"):
        pair = pair.strip()
        if "=" in pair:
            key, _, value = pair.partition("=")
            cookies[key.strip()] = value.strip()
    return cookies
