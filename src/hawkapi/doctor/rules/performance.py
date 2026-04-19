"""Performance rules: DOC030–DOC033."""

from __future__ import annotations

import inspect
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity, docs_url

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI

_IO_PARAM_NAMES = frozenset({"db", "session", "http_client", "redis", "conn", "client"})


@dataclass(frozen=True, slots=True)
class _DOC030:
    id: str = "DOC030"
    category: str = "performance"
    severity: Severity = Severity.INFO
    title: str = "debug=True on HawkAPI in a production-like environment"
    docs_url: str = docs_url("DOC030")

    def check(self, app: HawkAPI) -> list[Finding]:
        if not app.debug:
            return []
        in_prod = os.environ.get("ENV", "").lower() == "production"
        severity = Severity.ERROR if in_prod else Severity.INFO
        return [
            Finding(
                rule_id=self.id,
                severity=severity,
                message="HawkAPI was initialised with debug=True. "
                "This enables verbose error responses and may leak internal details.",
                fix="Set debug=False (or remove it) for production deployments.",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC031:
    id: str = "DOC031"
    category: str = "performance"
    severity: Severity = Severity.WARN
    title: str = "GZipMiddleware absent and routes return large payloads"
    docs_url: str = docs_url("DOC031")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.gzip import GZipMiddleware

        has_gzip = any(
            entry.cls is GZipMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_gzip:
            return []
        large_routes: list[str] = []
        for route in app.routes:
            model = route.response_model
            if model is None:
                continue
            try:
                import msgspec  # pyright: ignore[reportMissingImports]

                if issubclass(model, msgspec.Struct):
                    fields = msgspec.structs.fields(model)
                    if len(fields) > 10:
                        large_routes.append(route.path)
            except Exception:  # noqa: S110
                pass
        if not large_routes:
            return []
        sample = large_routes[:3]
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message=f"GZipMiddleware is not installed and {len(large_routes)} "
                f"route(s) use large response models (>10 fields): " + ", ".join(sample),
                fix="Add app.add_middleware(GZipMiddleware, minimum_size=1000).",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC032:
    id: str = "DOC032"
    category: str = "performance"
    severity: Severity = Severity.WARN
    title: str = "Handler returning bare dict/list without response_model"
    docs_url: str = docs_url("DOC032")

    def check(self, app: HawkAPI) -> list[Finding]:
        findings: list[Finding] = []
        for route in app.routes:
            if route.response_model is not None:
                continue
            try:
                hints = inspect.get_annotations(route.handler, eval_str=True)
            except Exception:
                try:
                    hints = getattr(route.handler, "__annotations__", {})
                except Exception:  # noqa: S112
                    continue
            ret = hints.get("return")
            if ret in (dict, list):
                methods = "/".join(sorted(route.methods - {"HEAD"}))
                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=f"Handler for {methods} {route.path} returns bare "
                        f"{ret.__name__}; output filtering is bypassed.",
                        fix="Add a msgspec.Struct return annotation or set "
                        "response_model= on the route.",
                        location=f"{methods} {route.path}",
                        docs_url=self.docs_url,
                    )
                )
        return findings


@dataclass(frozen=True, slots=True)
class _DOC033:
    id: str = "DOC033"
    category: str = "performance"
    severity: Severity = Severity.INFO
    title: str = "No bulkhead on heavy I/O routes"
    docs_url: str = docs_url("DOC033")

    def check(self, app: HawkAPI) -> list[Finding]:
        findings: list[Finding] = []
        for route in app.routes:
            try:
                sig = inspect.signature(route.handler)
            except (ValueError, TypeError):
                continue
            io_params = [p for p in sig.parameters if p.lower() in _IO_PARAM_NAMES]
            if not io_params:
                continue
            has_bulkhead = route.middleware is not None and any(
                (cls if isinstance(cls, type) else cls[0]).__name__ == "BulkheadMiddleware"
                for cls in route.middleware
            )
            if has_bulkhead:
                continue
            methods = "/".join(sorted(route.methods - {"HEAD"}))
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"{methods} {route.path} has I/O params "
                    f"({', '.join(io_params)}) but no bulkhead configured.",
                    fix="Wrap the route with @bulkhead(...) or add per-route "
                    "BulkheadMiddleware to limit concurrency.",
                    location=f"{methods} {route.path}",
                    docs_url=self.docs_url,
                )
            )
        return findings


DOC030 = _DOC030()
DOC031 = _DOC031()
DOC032 = _DOC032()
DOC033 = _DOC033()

PERFORMANCE_RULES: list[Any] = [DOC030, DOC031, DOC032, DOC033]
