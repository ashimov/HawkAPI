"""Security rules: DOC010–DOC014."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hawkapi.doctor._types import Finding, Severity, docs_url

if TYPE_CHECKING:
    from hawkapi.app import HawkAPI


@dataclass(frozen=True, slots=True)
class _DOC010:
    id: str = "DOC010"
    category: str = "security"
    severity: Severity = Severity.ERROR
    title: str = "CORS allows '*' in production"
    docs_url: str = docs_url("DOC010")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.cors import CORSMiddleware

        for entry in app._middleware_stack:  # pyright: ignore[reportPrivateUsage]
            if entry.cls is CORSMiddleware:
                origins: Any = entry.kwargs.get("allow_origins", ["*"])
                if "*" in origins:
                    return [
                        Finding(
                            rule_id=self.id,
                            severity=self.severity,
                            message="CORSMiddleware allows all origins ('*'). "
                            "This exposes all endpoints to any origin.",
                            fix="Whitelist specific origins in "
                            "CORSMiddleware(allow_origins=[...]).",
                            docs_url=self.docs_url,
                        )
                    ]
        return []


@dataclass(frozen=True, slots=True)
class _DOC011:
    id: str = "DOC011"
    category: str = "security"
    severity: Severity = Severity.WARN
    title: str = "CSRFMiddleware not installed but state-changing routes exist"
    docs_url: str = docs_url("DOC011")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.csrf import CSRFMiddleware

        state_methods = {"POST", "PUT", "PATCH", "DELETE"}
        has_state_route = any(bool(route.methods & state_methods) for route in app.routes)
        if not has_state_route:
            return []
        has_csrf = any(
            entry.cls is CSRFMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_csrf:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="State-changing routes (POST/PUT/PATCH/DELETE) exist but "
                "CSRFMiddleware is not installed.",
                fix="Add app.add_middleware(CSRFMiddleware, secret=...) to protect "
                "browser-facing endpoints.",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC012:
    id: str = "DOC012"
    category: str = "security"
    severity: Severity = Severity.WARN
    title: str = "TrustedProxyMiddleware missing behind a known proxy"
    docs_url: str = docs_url("DOC012")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.trusted_proxy import TrustedProxyMiddleware

        has_trusted_proxy = any(
            entry.cls is TrustedProxyMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_trusted_proxy:
            return []
        proxy_env = os.environ.get("FORWARDED_ALLOW_IPS") or os.environ.get("PROXY_HEADERS")
        if not proxy_env:
            return []
        return [
            Finding(
                rule_id=self.id,
                severity=self.severity,
                message="Proxy header env vars are set but TrustedProxyMiddleware "
                "is not installed. X-Forwarded-* headers may be spoofed.",
                fix="Add app.add_middleware(TrustedProxyMiddleware, "
                "trusted_hosts=[...]) to validate proxy headers.",
                docs_url=self.docs_url,
            )
        ]


@dataclass(frozen=True, slots=True)
class _DOC013:
    id: str = "DOC013"
    category: str = "security"
    severity: Severity = Severity.ERROR
    title: str = "Hardcoded placeholder secrets detected"
    docs_url: str = docs_url("DOC013")

    _PLACEHOLDERS: frozenset[str] = frozenset(
        {"changeme", "secret", "password", "dev", "insecure", "test"}
    )

    def check(self, app: HawkAPI) -> list[Finding]:
        findings: list[Finding] = []
        state = getattr(app, "state", None)
        if state is None:
            return findings
        for attr in dir(state):
            if attr.startswith("_"):
                continue
            try:
                val = getattr(state, attr)
            except Exception:  # noqa: S112
                continue
            if isinstance(val, str) and val.lower() in self._PLACEHOLDERS:
                findings.append(
                    Finding(
                        rule_id=self.id,
                        severity=self.severity,
                        message=f"app.state.{attr} contains a placeholder value "
                        f"'{val}'. Do not use in production.",
                        fix="Replace with a secret loaded from environment variables "
                        "or a secrets manager.",
                        location=f"app.state.{attr}",
                        docs_url=self.docs_url,
                    )
                )
        return findings


@dataclass(frozen=True, slots=True)
class _DOC014:
    id: str = "DOC014"
    category: str = "security"
    severity: Severity = Severity.INFO
    title: str = "HTTPSRedirectMiddleware absent"
    docs_url: str = docs_url("DOC014")

    def check(self, app: HawkAPI) -> list[Finding]:
        from hawkapi.middleware.https_redirect import HTTPSRedirectMiddleware

        has_https = any(
            entry.cls is HTTPSRedirectMiddleware
            for entry in app._middleware_stack  # pyright: ignore[reportPrivateUsage]
        )
        if has_https:
            return []
        in_prod = os.environ.get("ENV", "").lower() == "production"
        severity = Severity.WARN if in_prod else Severity.INFO
        return [
            Finding(
                rule_id=self.id,
                severity=severity,
                message="HTTPSRedirectMiddleware is not installed. HTTP requests "
                "will not be redirected to HTTPS.",
                fix="Add app.add_middleware(HTTPSRedirectMiddleware) to enforce HTTPS.",
                docs_url=self.docs_url,
            )
        ]


DOC010 = _DOC010()
DOC011 = _DOC011()
DOC012 = _DOC012()
DOC013 = _DOC013()
DOC014 = _DOC014()

SECURITY_RULES: list[Any] = [DOC010, DOC011, DOC012, DOC013, DOC014]
