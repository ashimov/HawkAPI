"""Tests for TestClient cookie jar, assertion helpers, and response improvements."""

import pytest

from hawkapi import HawkAPI, Response
from hawkapi.testing.client import HTTPStatusError, TestClient


def _cookie_app() -> HawkAPI:
    """App that sets and reads cookies."""
    app = HawkAPI(openapi_url=None)

    @app.get("/set-cookie")
    async def set_cookie():
        return Response(
            content=b"ok",
            status_code=200,
            headers={"set-cookie": "session=abc123; Path=/"},
        )

    @app.get("/set-multi-cookie")
    async def set_multi_cookie():
        return Response(
            content=b"ok",
            status_code=200,
            headers={"set-cookie": "token=xyz789; Path=/"},
        )

    @app.get("/read-cookie")
    async def read_cookie(request):
        cookie_header = request.headers.get("cookie", "")
        return Response(
            content=cookie_header.encode(),
            status_code=200,
        )

    return app


class TestCookieJar:
    def test_cookies_persist_across_requests(self):
        """Cookie jar stores Set-Cookie values and sends them in subsequent requests."""
        app = _cookie_app()
        client = TestClient(app)

        # First request sets a cookie
        resp = client.get("/set-cookie")
        assert resp.status_code == 200
        assert "session" in client.cookies
        assert client.cookies["session"] == "abc123"

        # Second request should include the cookie
        resp2 = client.get("/read-cookie")
        assert "session=abc123" in resp2.text

    def test_manual_cookie_setting(self):
        """Cookies can be set manually on the client."""
        app = _cookie_app()
        client = TestClient(app)

        client.cookies["manual"] = "value123"
        resp = client.get("/read-cookie")
        assert "manual=value123" in resp.text

    def test_cookie_clear(self):
        """client.cookies.clear() removes all stored cookies."""
        app = _cookie_app()
        client = TestClient(app)

        client.cookies["a"] = "1"
        client.cookies["b"] = "2"
        assert len(client.cookies) == 2

        client.cookies.clear()
        assert len(client.cookies) == 0

        resp = client.get("/read-cookie")
        assert resp.text == ""

    def test_cookies_accumulate_from_multiple_responses(self):
        """Cookies from different responses accumulate in the jar."""
        app = _cookie_app()
        client = TestClient(app)

        client.get("/set-cookie")
        client.get("/set-multi-cookie")

        assert client.cookies["session"] == "abc123"
        assert client.cookies["token"] == "xyz789"

        resp = client.get("/read-cookie")
        assert "session=abc123" in resp.text
        assert "token=xyz789" in resp.text


class TestResponseCookies:
    def test_response_cookies_parses_set_cookie(self):
        """response.cookies returns parsed Set-Cookie values."""
        app = _cookie_app()
        client = TestClient(app)

        resp = client.get("/set-cookie")
        assert resp.cookies == {"session": "abc123"}

    def test_response_cookies_empty_when_no_set_cookie(self):
        """response.cookies returns empty dict when no Set-Cookie header."""
        app = _cookie_app()
        client = TestClient(app)

        resp = client.get("/read-cookie")
        assert resp.cookies == {}


class TestCaseInsensitiveHeaders:
    def test_header_access_case_insensitive(self):
        """Headers can be accessed regardless of case."""
        app = HawkAPI(openapi_url=None)

        @app.get("/headers")
        async def with_headers():
            return Response(
                content=b"ok",
                status_code=200,
                headers={"X-Custom-Header": "myvalue"},
            )

        client = TestClient(app)
        resp = client.get("/headers")

        # All case variants should work
        assert resp.headers["x-custom-header"] == "myvalue"
        assert resp.headers["X-Custom-Header"] == "myvalue"
        assert resp.headers["X-CUSTOM-HEADER"] == "myvalue"

    def test_header_get_case_insensitive(self):
        """headers.get() works case-insensitively."""
        app = HawkAPI(openapi_url=None)

        @app.get("/h")
        async def h():
            return Response(
                content=b"ok",
                status_code=200,
                headers={"Content-Type": "text/html"},
            )

        client = TestClient(app)
        resp = client.get("/h")
        assert resp.headers.get("content-type") is not None
        assert resp.headers.get("CONTENT-TYPE") is not None

    def test_header_contains_case_insensitive(self):
        """'in' operator works case-insensitively on headers."""
        app = HawkAPI(openapi_url=None)

        @app.get("/c")
        async def c():
            return Response(
                content=b"ok",
                status_code=200,
                headers={"X-Token": "abc"},
            )

        client = TestClient(app)
        resp = client.get("/c")
        assert "x-token" in resp.headers
        assert "X-Token" in resp.headers
        assert "X-TOKEN" in resp.headers
        assert "nonexistent" not in resp.headers


class TestRaiseForStatus:
    def test_raise_for_status_on_4xx(self):
        """raise_for_status raises HTTPStatusError on 4xx."""
        app = HawkAPI(openapi_url=None)
        client = TestClient(app)

        # 404 from missing route
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

        with pytest.raises(HTTPStatusError) as exc_info:
            resp.raise_for_status()
        assert exc_info.value.status_code == 404
        assert exc_info.value.response is resp

    def test_raise_for_status_on_5xx(self):
        """raise_for_status raises HTTPStatusError on 5xx."""
        app = HawkAPI(openapi_url=None)

        @app.get("/error")
        async def error():
            return Response(content=b"fail", status_code=500)

        client = TestClient(app)
        resp = client.get("/error")

        with pytest.raises(HTTPStatusError):
            resp.raise_for_status()

    def test_raise_for_status_noop_on_success(self):
        """raise_for_status does nothing on 2xx."""
        app = HawkAPI(openapi_url=None)

        @app.get("/ok")
        async def ok():
            return {"status": "ok"}

        client = TestClient(app)
        resp = client.get("/ok")
        resp.raise_for_status()  # Should not raise


class TestIsSuccessIsRedirect:
    def test_is_success_on_200(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/ok")
        async def ok():
            return {"status": "ok"}

        client = TestClient(app)
        resp = client.get("/ok")
        assert resp.is_success is True
        assert resp.is_redirect is False

    def test_is_success_on_201(self):
        app = HawkAPI(openapi_url=None)

        @app.post("/create")
        async def create():
            return {"id": 1}

        client = TestClient(app)
        resp = client.post("/create", json={})
        assert resp.is_success is True

    def test_is_redirect_on_3xx(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/redir")
        async def redir():
            return Response(content=b"", status_code=302, headers={"location": "/target"})

        client = TestClient(app)
        resp = client.get("/redir")
        assert resp.is_redirect is True
        assert resp.is_success is False

    def test_is_not_success_on_4xx(self):
        app = HawkAPI(openapi_url=None)
        client = TestClient(app)
        resp = client.get("/missing")
        assert resp.is_success is False
        assert resp.is_redirect is False

    def test_is_not_success_on_5xx(self):
        app = HawkAPI(openapi_url=None)

        @app.get("/err")
        async def err():
            return Response(content=b"err", status_code=503)

        client = TestClient(app)
        resp = client.get("/err")
        assert resp.is_success is False
        assert resp.is_redirect is False
