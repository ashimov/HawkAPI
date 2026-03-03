"""Tests for Request, Headers, QueryParams, State."""

import pytest

from hawkapi.requests.headers import Headers
from hawkapi.requests.query_params import QueryParams
from hawkapi.requests.request import Request
from hawkapi.requests.state import State


class TestHeaders:
    def test_case_insensitive_get(self):
        raw = [(b"Content-Type", b"application/json"), (b"X-Custom", b"value")]
        headers = Headers(raw)

        assert headers.get("content-type") == "application/json"
        assert headers.get("Content-Type") == "application/json"
        assert headers.get("CONTENT-TYPE") == "application/json"

    def test_get_default(self):
        headers = Headers([])
        assert headers.get("missing") is None
        assert headers.get("missing", "default") == "default"

    def test_getitem(self):
        headers = Headers([(b"x-key", b"val")])
        assert headers["x-key"] == "val"

    def test_getitem_missing(self):
        headers = Headers([])
        with pytest.raises(KeyError):
            headers["missing"]

    def test_contains(self):
        headers = Headers([(b"x-key", b"val")])
        assert "x-key" in headers
        assert "X-Key" in headers
        assert "missing" not in headers

    def test_getlist(self):
        raw = [(b"Set-Cookie", b"a=1"), (b"Set-Cookie", b"b=2")]
        headers = Headers(raw)
        assert headers.getlist("Set-Cookie") == ["a=1", "b=2"]

    def test_len(self):
        headers = Headers([(b"a", b"1"), (b"b", b"2")])
        assert len(headers) == 2

    def test_iter(self):
        raw = [(b"a", b"1"), (b"b", b"2")]
        headers = Headers(raw)
        items = list(headers)
        assert items == [("a", "1"), ("b", "2")]


class TestQueryParams:
    def test_parse_simple(self):
        qp = QueryParams(b"name=Alice&age=30")
        assert qp.get("name") == "Alice"
        assert qp.get("age") == "30"

    def test_get_default(self):
        qp = QueryParams(b"")
        assert qp.get("missing") is None
        assert qp.get("missing", "default") == "default"

    def test_multi_value(self):
        qp = QueryParams(b"tag=a&tag=b&tag=c")
        assert qp.getlist("tag") == ["a", "b", "c"]
        assert qp.get("tag") == "a"  # First value

    def test_getitem(self):
        qp = QueryParams(b"key=value")
        assert qp["key"] == "value"

    def test_getitem_missing(self):
        qp = QueryParams(b"")
        with pytest.raises(KeyError):
            qp["missing"]

    def test_contains(self):
        qp = QueryParams(b"key=value")
        assert "key" in qp
        assert "missing" not in qp

    def test_to_dict(self):
        qp = QueryParams(b"a=1&b=2")
        assert qp.to_dict() == {"a": "1", "b": "2"}

    def test_empty_query_string(self):
        qp = QueryParams(b"")
        assert qp.to_dict() == {}
        assert len(qp) == 0


class TestState:
    def test_set_get(self):
        state = State()
        state.user = "Alice"
        assert state.user == "Alice"

    def test_missing_attr(self):
        state = State()
        with pytest.raises(AttributeError):
            _ = state.nonexistent

    def test_del(self):
        state = State()
        state.key = "value"
        del state.key
        with pytest.raises(AttributeError):
            _ = state.key

    def test_contains(self):
        state = State()
        state.key = "value"
        assert "key" in state
        assert "missing" not in state


class TestRequest:
    def _make_scope(self, **overrides):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"",
            "headers": [],
        }
        scope.update(overrides)
        return scope

    async def _empty_receive(self):
        return {"type": "http.request", "body": b"", "more_body": False}

    @pytest.mark.asyncio
    async def test_method(self):
        req = Request(self._make_scope(method="POST"), self._empty_receive)
        assert req.method == "POST"

    @pytest.mark.asyncio
    async def test_path(self):
        req = Request(self._make_scope(path="/api/users"), self._empty_receive)
        assert req.path == "/api/users"

    @pytest.mark.asyncio
    async def test_headers_lazy(self):
        scope = self._make_scope(headers=[(b"x-custom", b"value")])
        req = Request(scope, self._empty_receive)
        assert req.headers.get("x-custom") == "value"

    @pytest.mark.asyncio
    async def test_query_params_lazy(self):
        scope = self._make_scope(query_string=b"page=2&limit=10")
        req = Request(scope, self._empty_receive)
        assert req.query_params.get("page") == "2"
        assert req.query_params.get("limit") == "10"

    @pytest.mark.asyncio
    async def test_path_params(self):
        req = Request(
            self._make_scope(),
            self._empty_receive,
            path_params={"user_id": 42},
        )
        assert req.path_params == {"user_id": 42}

    @pytest.mark.asyncio
    async def test_body(self):
        body_data = b'{"name": "Alice"}'

        async def receive():
            return {"type": "http.request", "body": body_data, "more_body": False}

        req = Request(self._make_scope(), receive)
        assert await req.body() == body_data

    @pytest.mark.asyncio
    async def test_json(self):
        body_data = b'{"name": "Alice"}'

        async def receive():
            return {"type": "http.request", "body": body_data, "more_body": False}

        req = Request(self._make_scope(), receive)
        data = await req.json()
        assert data == {"name": "Alice"}

    @pytest.mark.asyncio
    async def test_cookies(self):
        scope = self._make_scope(headers=[(b"cookie", b"session=abc123; theme=dark")])
        req = Request(scope, self._empty_receive)
        assert req.cookies == {"session": "abc123", "theme": "dark"}

    @pytest.mark.asyncio
    async def test_state(self):
        req = Request(self._make_scope(), self._empty_receive)
        req.state.user = "Alice"
        assert req.state.user == "Alice"
