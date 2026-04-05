"""CSRF (Cross-Site Request Forgery) protection middleware.

Implements the double-submit cookie pattern: a CSRF token is stored in a
cookie and must be echoed back via a header (or form field) on unsafe
requests. The comparison uses ``hmac.compare_digest`` for timing safety.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any
from urllib.parse import parse_qs

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware
from hawkapi.responses.response import Response
from hawkapi.serialization.encoder import encode_response


class CSRFMiddleware(Middleware):
    """Double-submit cookie CSRF protection.

    Safe methods (GET, HEAD, OPTIONS) pass through.
    Unsafe methods require a CSRF token that matches the cookie value.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret: str,
        cookie_name: str = "csrftoken",
        header_name: str = "x-csrf-token",
        safe_methods: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"}),
        cookie_path: str = "/",
        cookie_httponly: bool = False,
        cookie_secure: bool = True,
        cookie_samesite: str = "lax",
    ) -> None:
        super().__init__(app)
        self._secret = secret
        self._cookie_name = cookie_name
        self._header_name = header_name.lower()
        self._header_name_bytes = self._header_name.encode("latin-1")
        self._safe_methods = safe_methods
        self._cookie_path = cookie_path
        self._cookie_httponly = cookie_httponly
        self._cookie_secure = cookie_secure
        self._cookie_samesite = cookie_samesite

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------

    def _generate_token(self) -> str:
        """Generate a CSRF token: HMAC-SHA256(secret, random) as url-safe string."""
        raw = secrets.token_urlsafe(32)
        sig = hmac.new(
            self._secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{raw}.{sig}"

    def _verify_token(self, token: str) -> bool:
        """Verify a token's HMAC signature is valid."""
        parts = token.split(".", 1)
        if len(parts) != 2:
            return False
        raw, sig = parts
        expected = hmac.new(
            self._secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(sig, expected)

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    def _get_cookie_value(self, scope: Scope) -> str | None:
        """Extract the CSRF cookie value from request headers."""
        for key, value in scope.get("headers", []):
            if key == b"cookie":
                cookie_str = value.decode("latin-1")
                for pair in cookie_str.split(";"):
                    pair = pair.strip()
                    if "=" in pair:
                        name, _, val = pair.partition("=")
                        if name.strip() == self._cookie_name:
                            return val.strip()
        return None

    def _build_set_cookie(self, token: str) -> bytes:
        """Build the Set-Cookie header value."""
        parts = [f"{self._cookie_name}={token}", f"Path={self._cookie_path}"]
        if self._cookie_httponly:
            parts.append("HttpOnly")
        if self._cookie_secure:
            parts.append("Secure")
        parts.append(f"SameSite={self._cookie_samesite}")
        return "; ".join(parts).encode("latin-1")

    # ------------------------------------------------------------------
    # Header / form extraction
    # ------------------------------------------------------------------

    def _get_header_token(self, scope: Scope) -> str | None:
        """Extract the CSRF token from the request header."""
        for key, value in scope.get("headers", []):
            if key == self._header_name_bytes:
                return value.decode("latin-1")
        return None

    async def _get_form_token(self, receive: Receive) -> tuple[str | None, bytes]:
        """Extract the CSRF token from URL-encoded form body.

        Returns (token, raw_body) so the body can be replayed.
        """
        body_parts: list[bytes] = []
        while True:
            message = await receive()
            body = message.get("body", b"")
            if body:
                body_parts.append(body)
            if not message.get("more_body", False):
                break
        raw_body = b"".join(body_parts)

        try:
            parsed = parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)
            tokens = parsed.get("csrf_token", [])
            return (tokens[0] if tokens else None, raw_body)
        except (UnicodeDecodeError, ValueError):
            return (None, raw_body)

    # ------------------------------------------------------------------
    # Error response
    # ------------------------------------------------------------------

    def _forbidden_response(self, detail: str) -> Response:
        return Response(
            content=encode_response(
                {
                    "type": "https://hawkapi.ashimov.com/errors/csrf",
                    "title": "CSRF Validation Failed",
                    "status": 403,
                    "detail": detail,
                }
            ),
            status_code=403,
            content_type="application/problem+json",
        )

    # ------------------------------------------------------------------
    # ASGI entry point
    # ------------------------------------------------------------------

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method: str = scope["method"]
        cookie_token = self._get_cookie_value(scope)

        # --- Safe methods: pass through, set cookie if missing ----------
        if method in self._safe_methods:
            if cookie_token is not None:
                # Cookie already exists — pass through unchanged
                await self.app(scope, receive, send)
                return

            # Generate a new token and inject it into the response
            new_token = self._generate_token()
            set_cookie_value = self._build_set_cookie(new_token)

            async def inject_cookie(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", set_cookie_value))
                    message = {**message, "headers": headers}
                await send(message)

            await self.app(scope, receive, inject_cookie)
            return

        # --- Unsafe methods: validate token -----------------------------
        if cookie_token is None:
            response = self._forbidden_response("CSRF cookie not set.")
            await response(scope, receive, send)
            return

        # Try header first
        submitted_token = self._get_header_token(scope)

        if submitted_token is None:
            # Fall back to form body
            submitted_token, raw_body = await self._get_form_token(receive)

            # Build a replay receive so downstream can read the body
            body_sent = False

            async def replay_receive() -> dict[str, Any]:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": raw_body, "more_body": False}
                return {"type": "http.request", "body": b"", "more_body": False}

            receive = replay_receive

        if submitted_token is None:
            response = self._forbidden_response("CSRF token missing.")
            await response(scope, receive, send)
            return

        if not hmac.compare_digest(submitted_token, cookie_token):
            response = self._forbidden_response("CSRF token mismatch.")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
