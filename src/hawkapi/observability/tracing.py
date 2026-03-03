"""OpenTelemetry tracing integration (lazy imports)."""

from __future__ import annotations

import contextlib
from typing import Any

_tracer: Any = None
_otel_available: bool | None = None


def is_otel_available() -> bool:
    """Check if OpenTelemetry is installed (cached)."""
    global _otel_available  # noqa: PLW0603
    if _otel_available is None:
        try:
            import opentelemetry  # type: ignore[import-not-found]  # noqa: F401

            _otel_available = True
        except ImportError:
            _otel_available = False
    return _otel_available


def get_tracer(service_name: str = "hawkapi") -> Any:
    """Get or create the OpenTelemetry tracer."""
    global _tracer  # noqa: PLW0603
    if _tracer is None and is_otel_available():
        from opentelemetry import trace  # noqa: I001  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

        _tracer = trace.get_tracer(service_name)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    return _tracer  # pyright: ignore[reportUnknownVariableType]


def start_span(name: str, attributes: dict[str, Any] | None = None) -> Any:
    """Start a trace span if OTel is available, otherwise return a no-op context manager."""
    tracer = get_tracer()
    if tracer is not None:
        return tracer.start_as_current_span(name, attributes=attributes or {})
    return contextlib.nullcontext()
