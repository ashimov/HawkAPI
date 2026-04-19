"""GrpcMount — lifecycle wrapper for a grpc.aio.Server."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import grpc
    import grpc.aio

logger = logging.getLogger("hawkapi.grpc")


class GrpcMount:
    """Thin lifecycle wrapper around a ``grpc.aio.Server``.

    Created and returned by ``HawkAPI.mount_grpc()``.
    Exposes ``.server``, ``.port``, ``.start()``, and ``.stop(grace)``.
    """

    def __init__(
        self,
        *,
        port: int,
        host: str,
        interceptors: Sequence[Any],
        ssl_credentials: Any,
        reflection: bool,
        reflection_service_names: Sequence[str] | None,
        options: Sequence[tuple[str, Any]],
        max_workers: int | None,
    ) -> None:
        self.port = port
        self._host = host
        self._interceptors = list(interceptors)
        self._ssl_credentials = ssl_credentials
        self._reflection = reflection
        self._reflection_service_names = reflection_service_names
        self._options = options
        self._max_workers = max_workers
        self._server: Any = None
        self._started = False
        # Pending (servicer, add_to_server) registrations — filled before _start
        self._pending: list[tuple[object, Callable[[object, Any], None]]] = []

    @property
    def server(self) -> Any:
        """The underlying ``grpc.aio.Server`` instance (available after start)."""
        return self._server

    def _add_servicer(
        self,
        servicer: object,
        add_to_server: Callable[[object, Any], None],
    ) -> None:
        """Queue a servicer for registration when the server starts."""
        self._pending.append((servicer, add_to_server))

    async def _start(self) -> None:
        """Create the gRPC server, register servicers, and start listening."""
        import grpc.aio  # noqa: PLC0415

        from hawkapi.grpc._reflection import enable_reflection  # noqa: PLC0415

        if self._started:
            return

        server: grpc.aio.Server = grpc.aio.server(
            interceptors=self._interceptors,
            options=list(self._options),
            maximum_concurrent_rpcs=None,
        )
        self._server = server

        # Register all queued servicers
        for servicer, add_fn in self._pending:
            add_fn(servicer, server)

        # Bind port
        addr = f"{self._host}:{self.port}"
        if self._ssl_credentials is not None:
            server.add_secure_port(addr, self._ssl_credentials)
        else:
            server.add_insecure_port(addr)

        # Optional reflection
        if self._reflection:
            enable_reflection(self._reflection_service_names, server)

        await server.start()
        self._started = True
        logger.info("gRPC server started on %s", addr)

    async def _stop(self, grace: float = 5.0) -> None:
        """Stop the gRPC server gracefully."""
        if self._server is None or not self._started:
            return
        await self._server.stop(grace)
        self._started = False
        logger.info("gRPC server stopped (grace=%.1fs)", grace)

    # Public aliases for direct use
    async def start(self) -> None:
        """Start the gRPC server (idempotent)."""
        await self._start()

    async def stop(self, grace: float = 5.0) -> None:
        """Stop the gRPC server (no-op if not started)."""
        await self._stop(grace)
