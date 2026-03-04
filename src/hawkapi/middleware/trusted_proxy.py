"""Trusted proxy middleware — process X-Forwarded-* headers from trusted sources."""

from __future__ import annotations

import ipaddress
from typing import Any

from hawkapi._types import ASGIApp, Receive, Scope, Send
from hawkapi.middleware.base import Middleware


class TrustedProxyMiddleware(Middleware):
    """Rewrite client IP, scheme, and host from X-Forwarded-* headers.

    Only processes forwarded headers when the immediate client IP is
    within one of the configured trusted proxy CIDR ranges.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_proxies: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.trusted_networks = [
            ipaddress.ip_network(cidr, strict=False) for cidr in (trusted_proxies or [])
        ]

    def _is_trusted(self, client_ip: str) -> bool:
        """Check if the client IP falls within any trusted CIDR range."""
        try:
            addr = ipaddress.ip_address(client_ip)
        except ValueError:
            return False
        return any(addr in network for network in self.trusted_networks)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        if client is None:
            await self.app(scope, receive, send)
            return

        client_ip = client[0]
        if not self._is_trusted(client_ip):
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = scope.get("headers", [])

        forwarded_for: str | None = None
        forwarded_proto: str | None = None
        forwarded_host: str | None = None

        for key, value in headers:
            lower_key = key.lower()
            if lower_key == b"x-forwarded-for":
                forwarded_for = value.decode("latin-1")
            elif lower_key == b"x-forwarded-proto":
                forwarded_proto = value.decode("latin-1")
            elif lower_key == b"x-forwarded-host":
                forwarded_host = value.decode("latin-1")

        new_scope: dict[str, Any] = dict(scope)

        # Rewrite client IP from X-Forwarded-For (take leftmost/first IP)
        if forwarded_for:
            real_ip = forwarded_for.split(",")[0].strip()
            try:
                ipaddress.ip_address(real_ip)
            except ValueError:
                pass
            else:
                new_scope["client"] = (real_ip, 0)

        # Rewrite scheme from X-Forwarded-Proto
        if forwarded_proto:
            new_scope["scheme"] = forwarded_proto.strip().lower()

        # Rewrite host header from X-Forwarded-Host
        if forwarded_host:
            new_host = forwarded_host.strip().encode("latin-1")
            new_headers: list[tuple[bytes, bytes]] = []
            for key, value in headers:
                if key.lower() == b"host":
                    new_headers.append((key, new_host))
                else:
                    new_headers.append((key, value))
            new_scope["headers"] = new_headers

        # Propagate mutations back so callers holding a reference to the
        # original scope dict observe the updated values.
        scope.update(new_scope)

        await self.app(new_scope, receive, send)
