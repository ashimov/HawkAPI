"""Tests for HTTP Basic authentication."""

import base64

import pytest

from hawkapi.requests.request import Request
from hawkapi.security.api_key import MissingCredentialError
from hawkapi.security.http_basic import HTTPBasic, HTTPBasicCredentials


def _make_request(headers=None):
    raw_headers = []
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw_headers,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


async def test_extracts_credentials():
    basic = HTTPBasic()
    encoded = base64.b64encode(b"user:pass").decode()
    request = _make_request({"Authorization": f"Basic {encoded}"})
    creds = await basic(request)
    assert isinstance(creds, HTTPBasicCredentials)
    assert creds.username == "user"
    assert creds.password == "pass"


async def test_missing_header_raises():
    basic = HTTPBasic()
    request = _make_request()
    with pytest.raises(MissingCredentialError):
        await basic(request)


async def test_invalid_scheme_raises():
    basic = HTTPBasic()
    request = _make_request({"Authorization": "Bearer token123"})
    with pytest.raises(MissingCredentialError):
        await basic(request)


async def test_invalid_base64_raises():
    basic = HTTPBasic()
    request = _make_request({"Authorization": "Basic !!!invalid"})
    with pytest.raises(MissingCredentialError):
        await basic(request)


async def test_no_colon_raises():
    basic = HTTPBasic()
    encoded = base64.b64encode(b"nocolon").decode()
    request = _make_request({"Authorization": f"Basic {encoded}"})
    with pytest.raises(MissingCredentialError):
        await basic(request)


async def test_no_auto_error_returns_none():
    basic = HTTPBasic(auto_error=False)
    request = _make_request()
    result = await basic(request)
    assert result is None


async def test_password_with_colon():
    basic = HTTPBasic()
    encoded = base64.b64encode(b"user:p@ss:word").decode()
    request = _make_request({"Authorization": f"Basic {encoded}"})
    creds = await basic(request)
    assert creds.username == "user"
    assert creds.password == "p@ss:word"


def test_openapi_scheme():
    basic = HTTPBasic()
    assert basic.openapi_scheme == {"type": "http", "scheme": "basic"}


def test_integration_with_app():
    from typing import Annotated

    from hawkapi import Depends, HawkAPI
    from hawkapi.testing import TestClient

    basic = HTTPBasic()
    app = HawkAPI(openapi_url=None)

    @app.get("/secure")
    async def secure(creds: Annotated[HTTPBasicCredentials, Depends(basic)]):
        return {"user": creds.username}

    client = TestClient(app)
    encoded = base64.b64encode(b"admin:secret").decode()
    resp = client.get("/secure", headers={"Authorization": f"Basic {encoded}"})
    assert resp.status_code == 200
    assert resp.json() == {"user": "admin"}
