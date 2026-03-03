"""Tests for the observability subsystem: logger, metrics, tracing, middleware."""

import json
import logging

import pytest

from hawkapi import HawkAPI
from hawkapi.observability.config import ObservabilityConfig
from hawkapi.observability.logger import StructuredFormatter, setup_structured_logging
from hawkapi.observability.metrics import InMemoryMetrics
from hawkapi.observability.tracing import get_tracer, is_otel_available, start_span
from hawkapi.testing import TestClient


class TestObservabilityConfig:
    def test_defaults(self):
        config = ObservabilityConfig()
        assert config.enable_tracing is True
        assert config.enable_logging is True
        assert config.enable_metrics is True
        assert config.log_level == "INFO"
        assert config.log_format == "json"
        assert config.trace_sample_rate == 1.0
        assert config.service_name == "hawkapi"
        assert config.metrics_prefix == "hawkapi"
        assert config.request_id_header == "x-request-id"

    def test_custom_config(self):
        config = ObservabilityConfig(
            enable_tracing=False,
            log_level="DEBUG",
            service_name="myapp",
        )
        assert config.enable_tracing is False
        assert config.log_level == "DEBUG"
        assert config.service_name == "myapp"

    def test_invalid_trace_sample_rate_too_high(self):
        with pytest.raises(ValueError, match="trace_sample_rate"):
            ObservabilityConfig(trace_sample_rate=1.5)

    def test_invalid_trace_sample_rate_negative(self):
        with pytest.raises(ValueError, match="trace_sample_rate"):
            ObservabilityConfig(trace_sample_rate=-0.1)

    def test_invalid_log_level(self):
        with pytest.raises(ValueError, match="log_level"):
            ObservabilityConfig(log_level="VERBOSE")

    def test_empty_service_name(self):
        with pytest.raises(ValueError, match="service_name"):
            ObservabilityConfig(service_name="")


class TestStructuredFormatter:
    def test_json_output(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="hawkapi",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["message"] == "test message"
        assert data["logger"] == "hawkapi"
        assert "timestamp" in data

    def test_extra_fields(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="hawkapi",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="request",
            args=(),
            exc_info=None,
        )
        record.request_id = "abc-123"  # type: ignore[attr-defined]
        record.method = "GET"  # type: ignore[attr-defined]
        record.status_code = 200  # type: ignore[attr-defined]
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "abc-123"
        assert data["method"] == "GET"
        assert data["status_code"] == 200

    def test_exception_info(self):
        formatter = StructuredFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            record = logging.LogRecord(
                name="hawkapi",
                level=logging.ERROR,
                pathname="test.py",
                lineno=1,
                msg="error",
                args=(),
                exc_info=sys.exc_info(),
            )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["exception"]["type"] == "ValueError"
        assert data["exception"]["message"] == "boom"


class TestSetupStructuredLogging:
    def test_creates_logger(self):
        logger = setup_structured_logging("DEBUG")
        assert logger.name == "hawkapi"
        assert logger.level == logging.DEBUG


class TestInMemoryMetrics:
    def test_empty(self):
        m = InMemoryMetrics()
        assert m.request_count == 0
        assert m.error_count == 0
        assert m.avg_duration_ms == 0.0

    def test_record_request(self):
        m = InMemoryMetrics()
        m.record_request("GET", "/", 200, 0.01)
        m.record_request("POST", "/items", 201, 0.02)
        assert m.request_count == 2
        assert m.error_count == 0

    def test_error_counting(self):
        m = InMemoryMetrics()
        m.record_request("GET", "/", 500, 0.1)
        m.record_request("GET", "/", 503, 0.2)
        m.record_request("GET", "/", 200, 0.05)
        assert m.error_count == 2

    def test_avg_duration(self):
        m = InMemoryMetrics()
        m.record_request("GET", "/", 200, 0.01)  # 10ms
        m.record_request("GET", "/", 200, 0.03)  # 30ms
        assert m.avg_duration_ms == pytest.approx(20.0)


class TestTracing:
    def test_otel_not_available(self):
        assert is_otel_available() is False

    def test_get_tracer_returns_none(self):
        assert get_tracer() is None

    def test_start_span_returns_nullcontext(self):
        import contextlib

        ctx = start_span("test")
        assert isinstance(ctx, contextlib.nullcontext)


class TestObservabilityMiddleware:
    def test_middleware_adds_request_id(self):
        app = HawkAPI(observability=True)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        client = TestClient(app)
        resp = client.get("/ping")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_middleware_preserves_existing_request_id(self):
        app = HawkAPI(observability=True)

        @app.get("/ping")
        async def ping():
            return {"pong": True}

        client = TestClient(app)
        resp = client.get("/ping", headers={"x-request-id": "my-custom-id"})
        assert resp.status_code == 200
        assert resp.headers["x-request-id"] == "my-custom-id"

    def test_middleware_with_custom_config(self):
        config = ObservabilityConfig(
            enable_tracing=False,
            enable_logging=False,
            enable_metrics=True,
        )
        app = HawkAPI(observability=config)

        @app.get("/test")
        async def test_route():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200

    def test_observability_disabled_by_default(self):
        app = HawkAPI()

        @app.get("/test")
        async def test_route():
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 200
        assert "x-request-id" not in resp.headers
