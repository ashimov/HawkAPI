"""Observability rules: DOC020–DOC023."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity, docs_url

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


@dataclass(frozen=True, slots=True)
class _DOC020:
    id: str = "DOC020"
    category: str = "observability"
    severity: Severity = Severity.WARN
    title: str = "No request-ID / observability middleware installed"
    docs_url: str = docs_url("DOC020")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.request_id import RequestIDMiddleware

        obs_names = {
            "RequestIDMiddleware",
            "StructuredLoggingMiddleware",
            "ObservabilityMiddleware",
        }
        has_obs = any(
            entry.cls.__name__ in obs_names or entry.cls is RequestIDMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_obs:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="No request-ID, structured logging, or observability "
                "middleware is installed.",
                fix="Add app.add_middleware(RequestIDMiddleware) or "
                "app.add_middleware(StructuredLoggingMiddleware).",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC021:
    id: str = "DOC021"
    category: str = "observability"
    severity: Severity = Severity.INFO
    title: str = "No /metrics endpoint"
    docs_url: str = docs_url("DOC021")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.prometheus import PrometheusMiddleware

        has_prometheus = any(
            entry.cls is PrometheusMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_prometheus:
            return []
        if importlib.util.find_spec("prometheus_client") is None:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="prometheus_client is installed but PrometheusMiddleware "
                "is not registered; /metrics endpoint is absent.",
                fix="Add app.add_middleware(PrometheusMiddleware) to expose metrics.",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC022:
    id: str = "DOC022"
    category: str = "observability"
    severity: Severity = Severity.INFO
    title: str = "No OTel wiring"
    docs_url: str = docs_url("DOC022")

    def check(self, app: HawkAPI) -> list[Finding]:
        if importlib.util.find_spec("opentelemetry") is None:
            return []
        has_otel = any(
            "otel" in entry.cls.__name__.lower() or "opentelemetry" in entry.cls.__name__.lower()
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        has_otel_plugin = any(
            "otel" in type(p).__name__.lower() or "opentelemetry" in type(p).__name__.lower()
            for p in app._plugins  # pyright: ignore[reportPrivateUsage]
        )
        if has_otel or has_otel_plugin:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="opentelemetry is installed but no OTel middleware or "
                "hawkapi-otel plugin is registered.",
                fix="Install hawkapi-otel and call app.add_plugin(OtelPlugin(...)).",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC023:
    id: str = "DOC023"
    category: str = "observability"
    severity: Severity = Severity.INFO
    title: str = "No Sentry wiring"
    docs_url: str = docs_url("DOC023")

    def check(self, app: HawkAPI) -> list[Finding]:
        if importlib.util.find_spec("sentry_sdk") is None:
            return []
        has_sentry = any(
            "sentry" in type(p).__name__.lower()
            for p in app._plugins  # pyright: ignore[reportPrivateUsage]
        )
        has_sentry_mw = any(
            "sentry" in entry.cls.__name__.lower()
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_sentry or has_sentry_mw:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="sentry_sdk is installed but no hawkapi-sentry plugin is registered.",
                fix="Install hawkapi-sentry and call app.add_plugin(SentryPlugin(...)).",
                docs_url=self.docs_url,
            )
        ]


DOC020 = _DOC020()
DOC021 = _DOC021()
DOC022 = _DOC022()
DOC023 = _DOC023()

OBSERVABILITY_RULES: list[Any] = [DOC020, DOC021, DOC022, DOC023]
