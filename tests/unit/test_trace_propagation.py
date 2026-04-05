"""Tests for W3C Trace Context propagation."""

from __future__ import annotations

from hawkapi import HawkAPI
from hawkapi.observability.tracing import (
    _parse_traceparent,
    _parse_tracestate,
    extract_context,
    inject_context,
)
from hawkapi.requests.request import Request
from hawkapi.testing import TestClient


class TestParseTraceparent:
    def test_valid_traceparent(self):
        value = "00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"
        result = _parse_traceparent(value)
        assert result is not None
        assert result["version"] == "00"
        assert result["trace_id"] == "4bf92f3577b16e0714f34b92bd2fa926"
        assert result["parent_id"] == "00f067aa0ba902b7"
        assert result["trace_flags"] == "01"

    def test_valid_traceparent_not_sampled(self):
        value = "00-abcdef1234567890abcdef1234567890-1234567890abcdef-00"
        result = _parse_traceparent(value)
        assert result is not None
        assert result["trace_flags"] == "00"

    def test_invalid_traceparent_wrong_format(self):
        assert _parse_traceparent("not-a-valid-traceparent") is None

    def test_invalid_traceparent_too_short(self):
        assert _parse_traceparent("00-abc-def-01") is None

    def test_invalid_traceparent_version_ff(self):
        value = "ff-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"
        assert _parse_traceparent(value) is None

    def test_invalid_traceparent_all_zero_trace_id(self):
        value = "00-00000000000000000000000000000000-00f067aa0ba902b7-01"
        assert _parse_traceparent(value) is None

    def test_invalid_traceparent_all_zero_parent_id(self):
        value = "00-4bf92f3577b16e0714f34b92bd2fa926-0000000000000000-01"
        assert _parse_traceparent(value) is None

    def test_traceparent_with_whitespace(self):
        value = "  00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01  "
        result = _parse_traceparent(value)
        assert result is not None
        assert result["trace_id"] == "4bf92f3577b16e0714f34b92bd2fa926"

    def test_invalid_traceparent_uppercase(self):
        # W3C spec requires lowercase hex
        value = "00-4BF92F3577B16E0714F34B92BD2FA926-00F067AA0BA902B7-01"
        assert _parse_traceparent(value) is None


class TestParseTracestate:
    def test_single_vendor(self):
        result = _parse_tracestate("congo=t61rcWkgMzE")
        assert result == "congo=t61rcWkgMzE"

    def test_multiple_vendors(self):
        result = _parse_tracestate("congo=t61rcWkgMzE,rojo=00f067aa0ba902b7")
        assert result == "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"

    def test_tracestate_with_whitespace(self):
        result = _parse_tracestate("  congo=t61rcWkgMzE , rojo=00f067aa0ba902b7  ")
        assert result == "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"

    def test_empty_tracestate(self):
        result = _parse_tracestate("")
        assert result == ""

    def test_tracestate_filters_invalid_entries(self):
        result = _parse_tracestate("congo=t61rcWkgMzE,invalid,rojo=val")
        assert result == "congo=t61rcWkgMzE,rojo=val"


class TestExtractContext:
    def test_extract_valid_traceparent(self):
        headers = [
            (b"traceparent", b"00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"),
        ]
        ctx = extract_context(headers)
        assert ctx["trace_id"] == "4bf92f3577b16e0714f34b92bd2fa926"
        assert len(ctx["span_id"]) == 16  # New span ID generated
        assert ctx["trace_flags"] == "01"

    def test_extract_invalid_traceparent_generates_new_ids(self):
        headers = [
            (b"traceparent", b"invalid-header"),
        ]
        ctx = extract_context(headers)
        assert len(ctx["trace_id"]) == 32
        assert len(ctx["span_id"]) == 16
        assert ctx["trace_flags"] == "01"

    def test_extract_missing_traceparent_generates_new_ids(self):
        headers = [
            (b"content-type", b"application/json"),
        ]
        ctx = extract_context(headers)
        assert len(ctx["trace_id"]) == 32
        assert len(ctx["span_id"]) == 16

    def test_extract_with_tracestate(self):
        headers = [
            (b"traceparent", b"00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"),
            (b"tracestate", b"congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"),
        ]
        ctx = extract_context(headers)
        assert ctx["trace_id"] == "4bf92f3577b16e0714f34b92bd2fa926"
        assert ctx["tracestate"] == "congo=t61rcWkgMzE,rojo=00f067aa0ba902b7"

    def test_extract_empty_headers(self):
        ctx = extract_context([])
        assert len(ctx["trace_id"]) == 32
        assert len(ctx["span_id"]) == 16

    def test_extract_generates_different_span_id_from_parent(self):
        headers = [
            (b"traceparent", b"00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"),
        ]
        ctx = extract_context(headers)
        # The span_id should be a new one, not the parent_id
        assert ctx["span_id"] != "00f067aa0ba902b7"


class TestInjectContext:
    def test_inject_adds_traceparent(self):
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
        ]
        result = inject_context(
            headers,
            trace_id="4bf92f3577b16e0714f34b92bd2fa926",
            span_id="00f067aa0ba902b7",
        )
        traceparent_headers = [v for k, v in result if k == b"traceparent"]
        assert len(traceparent_headers) == 1
        assert traceparent_headers[0] == b"00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01"

    def test_inject_adds_tracestate_when_present(self):
        headers: list[tuple[bytes, bytes]] = []
        result = inject_context(
            headers,
            trace_id="4bf92f3577b16e0714f34b92bd2fa926",
            span_id="00f067aa0ba902b7",
            tracestate="congo=t61rcWkgMzE",
        )
        tracestate_headers = [v for k, v in result if k == b"tracestate"]
        assert len(tracestate_headers) == 1
        assert tracestate_headers[0] == b"congo=t61rcWkgMzE"

    def test_inject_no_tracestate_when_empty(self):
        headers: list[tuple[bytes, bytes]] = []
        result = inject_context(
            headers,
            trace_id="4bf92f3577b16e0714f34b92bd2fa926",
            span_id="00f067aa0ba902b7",
            tracestate="",
        )
        tracestate_headers = [v for k, v in result if k == b"tracestate"]
        assert len(tracestate_headers) == 0

    def test_inject_preserves_existing_headers(self):
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"x-custom", b"value"),
        ]
        result = inject_context(
            headers,
            trace_id="abcd" * 8,
            span_id="1234" * 4,
        )
        # Original headers still present
        assert (b"content-type", b"application/json") in result
        assert (b"x-custom", b"value") in result


class TestTracePropagationInScope:
    def test_trace_id_and_span_id_in_scope(self):
        app = HawkAPI(observability=True)

        @app.get("/trace")
        async def trace_route(request: Request) -> dict:
            return {
                "trace_id": request.scope.get("trace_id", ""),
                "span_id": request.scope.get("span_id", ""),
            }

        client = TestClient(app)
        resp = client.get(
            "/trace",
            headers={
                "traceparent": "00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "4bf92f3577b16e0714f34b92bd2fa926"
        assert len(data["span_id"]) == 16

    def test_trace_id_generated_when_no_traceparent(self):
        app = HawkAPI(observability=True)

        @app.get("/trace")
        async def trace_route(request: Request) -> dict:
            return {
                "trace_id": request.scope.get("trace_id", ""),
                "span_id": request.scope.get("span_id", ""),
            }

        client = TestClient(app)
        resp = client.get("/trace")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trace_id"]) == 32
        assert len(data["span_id"]) == 16

    def test_traceparent_in_response_headers(self):
        app = HawkAPI(observability=True)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        client = TestClient(app)
        resp = client.get(
            "/ping",
            headers={
                "traceparent": "00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01",
            },
        )
        assert resp.status_code == 200
        assert "traceparent" in resp.headers

    def test_works_without_otel_installed(self):
        """Trace context works with manual fallback when OTel is not installed."""
        app = HawkAPI(observability=True)

        @app.get("/test")
        async def test_route(request: Request) -> dict:
            return {"trace_id": request.scope.get("trace_id", "")}

        client = TestClient(app)
        resp = client.get(
            "/test",
            headers={
                "traceparent": "00-abcdef1234567890abcdef1234567890-1234567890abcdef-01",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["trace_id"] == "abcdef1234567890abcdef1234567890"
