"""Correctness rules: DOC040–DOC042."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity, docs_url

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI

_AUTH_NAME_HINTS = frozenset({"auth", "bearer", "jwt", "token", "oauth"})


@dataclass(frozen=True, slots=True)
class _DOC040:
    id: str = "DOC040"
    category: str = "correctness"
    severity: Severity = Severity.INFO
    title: str = "Route handler missing return annotation"
    docs_url: str = docs_url("DOC040")

    def check(self, app: HawkAPI) -> list[Finding]:
        findings: list[Finding] = []
        for route in app.routes:
            if not route.include_in_schema:
                continue
            if route.response_model is not None:
                continue
            try:
                hints = inspect.get_annotations(route.handler, eval_str=True)
            except Exception:
                try:
                    hints = getattr(route.handler, "__annotations__", {})
                except Exception:
                    hints = {}
            if "return" not in hints:
                methods = "/".join(sorted(route.methods - {"HEAD"}))
                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=f"Handler for {methods} {route.path} has no return "
                        "annotation; response_model cannot be auto-inferred.",
                        fix="Add a return type annotation (e.g. -> MyStruct) to "
                        "enable auto-inferred response_model.",
                        location=f"{methods} {route.path}",
                        docs_url=self.docs_url,
                    )
                )
        return findings


@dataclass(frozen=True, slots=True)
class _DOC041:
    id: str = "DOC041"
    category: str = "correctness"
    severity: Severity = Severity.INFO
    title: str = "Route without docstring or summary="
    docs_url: str = docs_url("DOC041")

    def check(self, app: HawkAPI) -> list[Finding]:
        findings: list[Finding] = []
        for route in app.routes:
            if not route.include_in_schema:
                continue
            if route.summary:
                continue
            if route.description:
                continue
            doc = getattr(route.handler, "__doc__", None)
            if doc and doc.strip():
                continue
            methods = "/".join(sorted(route.methods - {"HEAD"}))
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"{methods} {route.path} has no docstring or summary; "
                    "the OpenAPI operation will have an empty summary.",
                    fix="Add a docstring to the handler function or pass summary= "
                    "to the route decorator.",
                    location=f"{methods} {route.path}",
                    docs_url=self.docs_url,
                )
            )
        return findings


@dataclass(frozen=True, slots=True)
class _DOC042:
    id: str = "DOC042"
    category: str = "correctness"
    severity: Severity = Severity.WARN
    title: str = "Suspicious middleware order: CORS after auth middleware"
    docs_url: str = docs_url("DOC042")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.cors import CORSMiddleware

        stack = list(app._middleware_stack)  # pyright: ignore[reportPrivateUsage]
        cors_idx: int | None = None
        auth_idx: int | None = None
        for i, entry in enumerate(stack):
            if entry.cls is CORSMiddleware:
                cors_idx = i
            name = entry.cls.__name__.lower()
            if any(hint in name for hint in _AUTH_NAME_HINTS):
                auth_idx = i
        if cors_idx is None or auth_idx is None:
            return []
        # Stack index 0 = outermost (added first). CORS should be outermost.
        # Warn if an auth middleware was added before CORS (lower index = outer).
        if auth_idx < cors_idx:
            return [
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"Authentication middleware (stack position {auth_idx}) "
                    f"appears before CORSMiddleware (position {cors_idx}). "
                    "CORS preflight OPTIONS requests may be rejected before "
                    "reaching the CORS handler.",
                    fix="Add CORSMiddleware before authentication middleware so "
                    "OPTIONS preflight requests are handled first.",
                    docs_url=self.docs_url,
                )
            ]
        return []


DOC040 = _DOC040()
DOC041 = _DOC041()
DOC042 = _DOC042()

CORRECTNESS_RULES: list[Any] = [DOC040, DOC041, DOC042]
