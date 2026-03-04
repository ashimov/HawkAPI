"""Tests for Prometheus metrics middleware."""

import pytest

pytest.importorskip("prometheus_client")

from prometheus_client import CollectorRegistry

from hawkapi import HawkAPI
from hawkapi.middleware.prometheus import PrometheusMiddleware


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


class TestPrometheusMiddleware:
    @pytest.fixture(autouse=True)
    def _fresh_registry(self):
        self.registry = CollectorRegistry()

    @pytest.mark.asyncio
    async def test_metrics_endpoint_registered(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/hello")
        async def hello():
            return {"msg": "hi"}

        resp = await _call_app(app, "GET", "/metrics")
        assert resp["status"] == 200
        assert b"http_requests_total" in resp["body"]

    @pytest.mark.asyncio
    async def test_request_counted(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        await _call_app(app, "GET", "/ping")
        await _call_app(app, "GET", "/ping")

        resp = await _call_app(app, "GET", "/metrics")
        body = resp["body"].decode()
        assert "http_requests_total" in body

    @pytest.mark.asyncio
    async def test_duration_histogram(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(PrometheusMiddleware, registry=self.registry)

        @app.get("/slow")
        async def slow():
            return {"ok": True}

        await _call_app(app, "GET", "/slow")

        resp = await _call_app(app, "GET", "/metrics")
        body = resp["body"].decode()
        assert "http_request_duration_seconds" in body

    @pytest.mark.asyncio
    async def test_custom_metrics_path(self):
        app = HawkAPI(openapi_url=None)
        app.add_middleware(
            PrometheusMiddleware, registry=self.registry, metrics_path="/custom-metrics"
        )

        @app.get("/test")
        async def test_handler():
            return {"ok": True}

        await _call_app(app, "GET", "/test")
        resp = await _call_app(app, "GET", "/custom-metrics")
        assert resp["status"] == 200
        assert b"http_requests_total" in resp["body"]
