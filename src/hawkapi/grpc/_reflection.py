"""Reflection enablement helper for gRPC servers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class ConfigurationError(Exception):
    """Raised when gRPC integration is misconfigured."""


def enable_reflection(
    service_names: Sequence[str] | None,
    server: Any,
) -> None:
    """Enable gRPC server reflection on *server*.

    Args:
        service_names: List of fully-qualified service names to expose via
            reflection (e.g. ``["mypackage.MyService"]``).  Pass
            ``grpc_reflection.v1alpha.reflection.SERVICE_NAME`` as one of the
            entries to also expose the reflection service itself.
        server: A ``grpc.aio.Server`` instance.

    Raises:
        ConfigurationError: When ``grpcio-reflection`` is not installed, or when
            ``service_names`` is ``None``/empty.
    """
    if not service_names:
        raise ConfigurationError(
            "reflection=True requires reflection_service_names to be set. "
            "Pass a list of fully-qualified service names, e.g.: "
            "reflection_service_names=['mypackage.MyService', "
            "grpc_reflection.v1alpha.reflection.SERVICE_NAME]"
        )

    try:
        from grpc_reflection.v1alpha import (  # type: ignore[import-untyped]  # noqa: PLC0415
            reflection,
        )
    except ImportError as exc:
        raise ConfigurationError(
            "gRPC reflection requires 'grpcio-reflection'. Install with: pip install hawkapi[grpc]"
        ) from exc

    reflection.enable_server_reflection(list(service_names), server)
