"""Tests for security schemes."""

import pytest

from hawkapi.requests.request import Request
from hawkapi.security.api_key import (
    APIKeyCookie,
    APIKeyHeader,
    APIKeyQuery,
    MissingCredentialError,
)
from hawkapi.security.http_bearer import HTTPBearer, HTTPBearerCredentials
from hawkapi.security.oauth2 import OAuth2PasswordBearer


def _make_request(headers=None, query_string=b"", cookies=None):
    """Create a minimal Request for testing."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))
    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        raw_headers.append((b"cookie", cookie_str.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": query_string,
        "headers": raw_headers,
        "root_path": "",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestAPIKeyHeader:
    @pytest.mark.asyncio
    async def test_extracts_key(self):
        scheme = APIKeyHeader(name="X-API-Key")
        request = _make_request(headers={"X-API-Key": "my-key"})
        result = await scheme(request)
        assert result == "my-key"

    @pytest.mark.asyncio
    async def test_missing_raises(self):
        scheme = APIKeyHeader(name="X-API-Key")
        request = _make_request()
        with pytest.raises(MissingCredentialError):
            await scheme(request)

    @pytest.mark.asyncio
    async def test_missing_returns_none_no_auto_error(self):
        scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
        request = _make_request()
        result = await scheme(request)
        assert result is None

    def test_openapi_scheme(self):
        scheme = APIKeyHeader(name="X-API-Key")
        oas = scheme.openapi_scheme
        assert oas["type"] == "apiKey"
        assert oas["in"] == "header"
        assert oas["name"] == "X-API-Key"


class TestAPIKeyQuery:
    @pytest.mark.asyncio
    async def test_extracts_key(self):
        scheme = APIKeyQuery(name="api_key")
        request = _make_request(query_string=b"api_key=secret123")
        result = await scheme(request)
        assert result == "secret123"

    @pytest.mark.asyncio
    async def test_missing_raises(self):
        scheme = APIKeyQuery(name="api_key")
        request = _make_request()
        with pytest.raises(MissingCredentialError):
            await scheme(request)


class TestAPIKeyCookie:
    @pytest.mark.asyncio
    async def test_extracts_key(self):
        scheme = APIKeyCookie(name="session")
        request = _make_request(cookies={"session": "abc123"})
        result = await scheme(request)
        assert result == "abc123"

    @pytest.mark.asyncio
    async def test_missing_raises(self):
        scheme = APIKeyCookie(name="session")
        request = _make_request()
        with pytest.raises(MissingCredentialError):
            await scheme(request)


class TestHTTPBearer:
    @pytest.mark.asyncio
    async def test_extracts_token(self):
        scheme = HTTPBearer()
        request = _make_request(headers={"Authorization": "Bearer mytoken123"})
        result = await scheme(request)
        assert isinstance(result, HTTPBearerCredentials)
        assert result.scheme == "Bearer"
        assert result.credentials == "mytoken123"

    @pytest.mark.asyncio
    async def test_missing_header_raises(self):
        scheme = HTTPBearer()
        request = _make_request()
        with pytest.raises(MissingCredentialError):
            await scheme(request)

    @pytest.mark.asyncio
    async def test_invalid_format_raises(self):
        scheme = HTTPBearer()
        request = _make_request(headers={"Authorization": "Basic abc123"})
        with pytest.raises(MissingCredentialError):
            await scheme(request)

    @pytest.mark.asyncio
    async def test_no_auto_error(self):
        scheme = HTTPBearer(auto_error=False)
        request = _make_request()
        result = await scheme(request)
        assert result is None

    def test_openapi_scheme(self):
        scheme = HTTPBearer()
        oas = scheme.openapi_scheme
        assert oas["type"] == "http"
        assert oas["scheme"] == "bearer"


class TestOAuth2PasswordBearer:
    @pytest.mark.asyncio
    async def test_extracts_token(self):
        scheme = OAuth2PasswordBearer(token_url="/auth/token")
        request = _make_request(headers={"Authorization": "Bearer my-jwt"})
        result = await scheme(request)
        assert result == "my-jwt"

    @pytest.mark.asyncio
    async def test_missing_raises(self):
        scheme = OAuth2PasswordBearer(token_url="/auth/token")
        request = _make_request()
        with pytest.raises(MissingCredentialError):
            await scheme(request)

    def test_openapi_scheme(self):
        scheme = OAuth2PasswordBearer(token_url="/auth/token")
        oas = scheme.openapi_scheme
        assert oas["type"] == "oauth2"
        assert oas["flows"]["password"]["tokenUrl"] == "/auth/token"
