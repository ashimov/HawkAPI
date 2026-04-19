"""Tests for hawkapi doctor: rules, runner, formatter, and CLI."""

from __future__ import annotations

import json
import sys

import pytest

from hawkapi import HawkAPI
from hawkapi.doctor._formatter import exit_code, format_human, format_json
from hawkapi.doctor._runner import run
from hawkapi.doctor._types import Finding, Severity
from hawkapi.doctor.rules import ALL_RULES
from hawkapi.doctor.rules.correctness import DOC040, DOC041, DOC042
from hawkapi.doctor.rules.deps import DOC051
from hawkapi.doctor.rules.observability import DOC020, DOC021
from hawkapi.doctor.rules.performance import DOC030, DOC031, DOC032
from hawkapi.doctor.rules.security import DOC010, DOC011, DOC012, DOC014

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_app() -> HawkAPI:
    """Minimal clean application — no middleware, no routes."""
    return HawkAPI(title="Test", debug=False)


def _app_with_post() -> HawkAPI:
    """App with a single POST route and no CSRF middleware."""
    app = HawkAPI()

    @app.post("/items")
    async def create_item() -> None:
        pass

    return app


# ---------------------------------------------------------------------------
# Security rules
# ---------------------------------------------------------------------------


class TestDOC010:
    def test_clean_no_cors(self) -> None:
        app = _clean_app()
        assert DOC010.check(app) == []

    def test_cors_wildcard_fires(self) -> None:
        from hawkapi.middleware.cors import CORSMiddleware

        app = _clean_app()
        app.add_middleware(CORSMiddleware, allow_origins=["*"])
        findings = DOC010.check(app)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR
        assert findings[0].rule_id == "DOC010"

    def test_cors_specific_origin_clean(self) -> None:
        from hawkapi.middleware.cors import CORSMiddleware

        app = _clean_app()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
        assert DOC010.check(app) == []


class TestDOC011:
    def test_no_routes_clean(self) -> None:
        app = _clean_app()
        assert DOC011.check(app) == []

    def test_post_without_csrf_fires(self) -> None:
        app = _app_with_post()
        findings = DOC011.check(app)
        assert len(findings) == 1
        assert findings[0].rule_id == "DOC011"
        assert findings[0].severity == Severity.WARN

    def test_post_with_csrf_clean(self) -> None:
        from hawkapi.middleware.csrf import CSRFMiddleware

        app = _app_with_post()
        app.add_middleware(CSRFMiddleware, secret="s3cr3t")
        assert DOC011.check(app) == []


class TestDOC012:
    def test_no_proxy_env_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
        monkeypatch.delenv("PROXY_HEADERS", raising=False)
        app = _clean_app()
        assert DOC012.check(app) == []

    def test_proxy_env_without_middleware_fires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.1")
        app = _clean_app()
        findings = DOC012.check(app)
        assert len(findings) == 1
        assert findings[0].rule_id == "DOC012"


class TestDOC014:
    def test_clean_info_severity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        app = _clean_app()
        findings = DOC014.check(app)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_production_env_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "production")
        app = _clean_app()
        findings = DOC014.check(app)
        assert len(findings) == 1
        assert findings[0].severity == Severity.WARN

    def test_https_redirect_installed_clean(self) -> None:
        from hawkapi.middleware.https_redirect import HTTPSRedirectMiddleware

        app = _clean_app()
        app.add_middleware(HTTPSRedirectMiddleware)
        assert DOC014.check(app) == []


# ---------------------------------------------------------------------------
# Observability rules
# ---------------------------------------------------------------------------


class TestDOC020:
    def test_no_middleware_fires(self) -> None:
        app = _clean_app()
        findings = DOC020.check(app)
        assert len(findings) == 1
        assert findings[0].rule_id == "DOC020"
        assert findings[0].severity == Severity.WARN

    def test_request_id_middleware_clean(self) -> None:
        from hawkapi.middleware.request_id import RequestIDMiddleware

        app = _clean_app()
        app.add_middleware(RequestIDMiddleware)
        assert DOC020.check(app) == []


class TestDOC021:
    def test_no_prometheus_client_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "prometheus_client", None)  # type: ignore[arg-type]
        app = _clean_app()
        assert DOC021.check(app) == []

    def test_prometheus_middleware_installed_clean(self) -> None:
        from hawkapi.middleware.prometheus import PrometheusMiddleware

        app = _clean_app()
        app.add_middleware(PrometheusMiddleware)
        assert DOC021.check(app) == []


# ---------------------------------------------------------------------------
# Performance rules
# ---------------------------------------------------------------------------


class TestDOC030:
    def test_debug_false_clean(self) -> None:
        app = _clean_app()
        assert DOC030.check(app) == []

    def test_debug_true_info_in_dev(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ENV", raising=False)
        app = HawkAPI(debug=True)
        findings = DOC030.check(app)
        assert len(findings) == 1
        assert findings[0].severity == Severity.INFO

    def test_debug_true_error_in_prod(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ENV", "production")
        app = HawkAPI(debug=True)
        findings = DOC030.check(app)
        assert len(findings) == 1
        assert findings[0].severity == Severity.ERROR


class TestDOC031:
    def test_no_large_models_clean(self) -> None:
        app = _clean_app()
        assert DOC031.check(app) == []

    def test_gzip_installed_clean(self) -> None:
        from hawkapi.middleware.gzip import GZipMiddleware

        app = _clean_app()
        app.add_middleware(GZipMiddleware)
        assert DOC031.check(app) == []


class TestDOC032:
    def test_no_routes_clean(self) -> None:
        app = _clean_app()
        assert DOC032.check(app) == []

    def test_bare_dict_return_fires(self) -> None:
        app = HawkAPI()

        @app.get("/items")
        async def list_items() -> dict:  # type: ignore[type-arg]
            return {}

        findings = DOC032.check(app)
        assert any(f.rule_id == "DOC032" for f in findings)

    def test_typed_return_clean(self) -> None:
        import msgspec

        class Item(msgspec.Struct):
            name: str

        app = HawkAPI()

        @app.get("/items")
        async def list_items() -> Item:
            return Item(name="x")

        assert DOC032.check(app) == []


# ---------------------------------------------------------------------------
# Correctness rules
# ---------------------------------------------------------------------------


class TestDOC040:
    def test_annotated_handler_clean(self) -> None:
        app = HawkAPI()

        @app.get("/ping")
        async def ping() -> dict:  # type: ignore[type-arg]
            return {}

        assert DOC040.check(app) == []

    def test_missing_annotation_fires(self) -> None:
        app = HawkAPI()

        async def no_annotation():  # type: ignore[return]
            return {}

        app.add_route("/x", no_annotation, methods={"GET"})
        findings = DOC040.check(app)
        assert any(f.rule_id == "DOC040" for f in findings)


class TestDOC041:
    def test_handler_with_docstring_clean(self) -> None:
        app = HawkAPI()

        @app.get("/ping")
        async def ping() -> None:
            """Ping endpoint."""

        assert DOC041.check(app) == []

    def test_handler_without_doc_fires(self) -> None:
        app = HawkAPI()

        async def no_doc() -> None:
            pass

        app.add_route("/x", no_doc, methods={"GET"})
        findings = DOC041.check(app)
        assert any(f.rule_id == "DOC041" for f in findings)


class TestDOC042:
    def test_no_auth_middleware_clean(self) -> None:
        from hawkapi.middleware.cors import CORSMiddleware

        app = _clean_app()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
        assert DOC042.check(app) == []

    def test_cors_first_then_security_headers_clean(self) -> None:
        """CORSMiddleware added first = outermost = correct order."""
        from hawkapi.middleware.cors import CORSMiddleware
        from hawkapi.middleware.security_headers import SecurityHeadersMiddleware

        app = _clean_app()
        app.add_middleware(CORSMiddleware, allow_origins=["https://example.com"])
        app.add_middleware(SecurityHeadersMiddleware)
        assert DOC042.check(app) == []


# ---------------------------------------------------------------------------
# Deps rules
# ---------------------------------------------------------------------------


class TestDOC051:
    def test_current_msgspec_clean(self) -> None:
        # hawkapi requires msgspec >= 0.19, so installed version is always fine
        assert DOC051.check(_clean_app()) == []


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestRunner:
    def test_run_returns_list(self) -> None:
        app = _clean_app()
        findings = run(app)
        assert isinstance(findings, list)

    def test_run_min_severity_filters(self) -> None:
        app = _clean_app()
        all_f = run(app, min_severity=Severity.INFO)
        warn_f = run(app, min_severity=Severity.WARN)
        error_f = run(app, min_severity=Severity.ERROR)
        assert len(all_f) >= len(warn_f) >= len(error_f)

    def test_run_broken_rule_does_not_crash(self) -> None:
        class BrokenRule:
            id = "DOC999"
            category = "test"
            severity = Severity.INFO
            title = "broken"
            docs_url = ""

            def check(self, app: HawkAPI) -> list[Finding]:
                raise RuntimeError("intentional failure")

        app = _clean_app()
        findings = run(app, rules=[BrokenRule()])
        assert len(findings) == 1
        assert "DOC999" in findings[0].message

    def test_all_rules_count(self) -> None:
        assert len(ALL_RULES) == 18


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------


class TestFormatter:
    def test_format_human_no_findings(self) -> None:
        out = format_human([], "test:app")
        assert "No findings" in out
        assert "exit 0" in out

    def test_format_human_with_error(self) -> None:
        f = Finding(rule_id="DOC010", severity=Severity.ERROR, message="bad cors")
        out = format_human([f], "test:app")
        assert "DOC010" in out
        assert "exit 2" in out

    def test_format_json_shape(self) -> None:
        f = Finding(
            rule_id="DOC010",
            severity=Severity.ERROR,
            message="bad cors",
            fix="fix it",
            location=None,
            docs_url="https://hawkapi.ashimov.com/doctor/DOC010",
        )
        raw = format_json([f], "app:app")
        data = json.loads(raw)
        assert data["app"] == "app:app"
        assert data["summary"]["errors"] == 1
        assert data["summary"]["warnings"] == 0
        assert data["summary"]["total"] == 1
        assert data["findings"][0]["severity"] == "error"
        assert data["findings"][0]["rule_id"] == "DOC010"

    def test_format_json_warn_severity_string(self) -> None:
        f = Finding(rule_id="DOC011", severity=Severity.WARN, message="no csrf")
        raw = format_json([f], "app:app")
        data = json.loads(raw)
        assert data["findings"][0]["severity"] == "warning"

    def test_exit_code_clean(self) -> None:
        assert exit_code([]) == 0

    def test_exit_code_warn(self) -> None:
        f = Finding(rule_id="X", severity=Severity.WARN, message="w")
        assert exit_code([f]) == 1

    def test_exit_code_error(self) -> None:
        f = Finding(rule_id="X", severity=Severity.ERROR, message="e")
        assert exit_code([f]) == 2


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


class TestCLI:
    def test_doctor_help(self) -> None:
        import io
        from contextlib import redirect_stdout

        from hawkapi.cli import main

        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                main(["doctor", "--help"])
        except SystemExit as exc:
            assert exc.code == 0
        output = buf.getvalue()
        assert "doctor" in output or "APP_SPEC" in output or "format" in output
