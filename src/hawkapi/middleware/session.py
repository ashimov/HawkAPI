"""Signed cookie-based session middleware.

Session data is stored in a signed cookie using HMAC-SHA256.
Data is serialized with msgspec.json, then base64url-encoded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from http.cookies import SimpleCookie
from typing import Any

import msgspec

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class SessionMiddleware(Middleware):
    """Signed cookie-based session middleware.

    Session data is stored in a signed, optionally encrypted cookie.
    Uses HMAC-SHA256 for signing to prevent tampering.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret_key: str,
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 3600,
        path: str = "/",
        httponly: bool = True,
        secure: bool = True,
        samesite: str = "lax",
    ) -> None:
        super().__init__(app)
        self._secret_key = secret_key.encode("utf-8")
        self._session_cookie = session_cookie
        self._max_age = max_age
        self._path = path
        self._httponly = httponly
        self._secure = secure
        self._samesite = samesite

    def _sign(self, data: bytes) -> str:
        """Create HMAC-SHA256 signature for data."""
        return hmac.new(self._secret_key, data, hashlib.sha256).hexdigest()

    def _encode_session(self, session_data: dict[str, Any]) -> str:
        """Serialize, base64-encode, and sign session data.

        Returns cookie value in format: base64(json_data).signature
        """
        json_bytes = msgspec.json.encode(session_data)
        b64_data = base64.urlsafe_b64encode(json_bytes).decode("ascii")
        timestamp = str(int(time.time()))
        payload = f"{b64_data}.{timestamp}"
        signature = self._sign(payload.encode("utf-8"))
        return f"{payload}.{signature}"

    def _decode_session(self, cookie_value: str) -> dict[str, Any]:
        """Verify signature and decode session data.

        Returns empty dict if cookie is invalid, tampered, or expired.
        """
        try:
            parts = cookie_value.split(".")
            if len(parts) != 3:
                return {}

            b64_data, timestamp_str, signature = parts

            # Verify signature
            payload = f"{b64_data}.{timestamp_str}"
            expected_signature = self._sign(payload.encode("utf-8"))
            if not hmac.compare_digest(signature, expected_signature):
                return {}

            # Check expiry
            timestamp = int(timestamp_str)
            if time.time() - timestamp > self._max_age:
                return {}

            # Decode data
            json_bytes = base64.urlsafe_b64decode(b64_data)
            data: Any = msgspec.json.decode(json_bytes)
            if not isinstance(data, dict):
                return {}
            return data  # type: ignore[return-value]
        except Exception:  # noqa: BLE001
            return {}

    def _get_cookie_value(self, scope: Scope) -> str | None:
        """Extract session cookie value from request headers."""
        for key, value in scope.get("headers", []):
            if key == b"cookie":
                cookie: SimpleCookie[str] = SimpleCookie(value.decode("latin-1"))  # pyright: ignore[reportInvalidTypeArguments]
                if self._session_cookie in cookie:
                    morsel = cookie[self._session_cookie]
                    return morsel.value
        return None

    def _build_set_cookie_header(self, cookie_value: str) -> bytes:
        """Build Set-Cookie header value."""
        parts = [f"{self._session_cookie}={cookie_value}"]
        parts.append(f"Max-Age={self._max_age}")
        parts.append(f"Path={self._path}")
        if self._httponly:
            parts.append("HttpOnly")
        if self._secure:
            parts.append("Secure")
        parts.append(f"SameSite={self._samesite}")
        return "; ".join(parts).encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Decode session from cookie (or start fresh)
        cookie_value = self._get_cookie_value(scope)
        session_data = self._decode_session(cookie_value) if cookie_value is not None else {}

        # Store session in scope; take a snapshot to detect changes
        scope["session"] = session_data
        initial_snapshot = msgspec.json.encode(session_data)

        async def send_with_session(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                # Check if session was modified
                current_data: dict[str, Any] = scope.get("session", {})
                current_snapshot = msgspec.json.encode(current_data)
                if current_snapshot != initial_snapshot:
                    # Session changed — set cookie
                    encoded = self._encode_session(current_data)
                    set_cookie = self._build_set_cookie_header(encoded)
                    headers = list(message.get("headers", []))
                    headers.append((b"set-cookie", set_cookie))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_session)
