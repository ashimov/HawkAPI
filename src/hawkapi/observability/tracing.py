"""OpenTelemetry tracing integration (lazy imports)."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import uuid
from typing import Any

_logger = logging.getLogger("hawkapi.tracing")

_tracer: Any = None
_otel_available: bool | None = None

# W3C Trace Context traceparent format:
# {version}-{trace-id}-{parent-id}-{trace-flags}
# Example: 00-4bf92f3577b16e0714f34b92bd2fa926-00f067aa0ba902b7-01
_TRACEPARENT_RE = re.compile(r"^([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


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


def _generate_trace_id() -> str:
    """Generate a random 32-hex-char trace ID."""
    return uuid.uuid4().hex


def _generate_span_id() -> str:
    """Generate a random 16-hex-char span/parent ID."""
    return os.urandom(8).hex()


def _parse_traceparent(value: str) -> dict[str, str] | None:
    """Parse a W3C traceparent header value.

    Returns a dict with version, trace_id, parent_id, trace_flags on success,
    or None if the value is invalid.
    """
    match = _TRACEPARENT_RE.match(value.strip())
    if match is None:
        return None

    version, trace_id, parent_id, trace_flags = match.groups()

    # version ff is invalid per spec
    if version == "ff":
        return None

    # All-zero trace-id or parent-id are invalid
    if trace_id == "0" * 32 or parent_id == "0" * 16:
        return None

    return {
        "version": version,
        "trace_id": trace_id,
        "parent_id": parent_id,
        "trace_flags": trace_flags,
    }


def _parse_tracestate(value: str) -> str:
    """Parse and normalize a W3C tracestate header value.

    Returns the cleaned tracestate string (vendor key=value pairs).
    """
    # Tracestate is a list of key=value pairs separated by commas
    parts: list[str] = []
    for item in value.split(","):
        item = item.strip()
        if item and "=" in item:
            parts.append(item)
    return ",".join(parts)


def extract_context(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    """Extract W3C trace context from incoming request headers.

    Returns a dict with trace_id, span_id, trace_flags, and tracestate.
    If traceparent is missing or invalid, generates new trace_id and span_id.
    """
    # Try OTel propagation first
    if is_otel_available():
        try:
            return _extract_context_otel(headers)
        except Exception:
            _logger.debug("OTel context extraction failed, falling back to manual", exc_info=True)

    return _extract_context_manual(headers)


def _extract_context_otel(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    """Extract context using OpenTelemetry propagation API."""
    from opentelemetry import context as otel_context  # noqa: I001  # pyright: ignore[reportMissingImports,reportUnknownVariableType]
    from opentelemetry import trace  # pyright: ignore[reportMissingImports,reportUnknownVariableType]
    from opentelemetry.context.propagation import get_global_textmap  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

    # Convert ASGI headers to a dict for OTel
    carrier: dict[str, str] = {}
    for key, value in headers:
        k = key.decode("latin-1").lower()
        carrier[k] = value.decode("latin-1")

    propagator = get_global_textmap()  # pyright: ignore[reportUnknownVariableType]
    ctx = propagator.extract(carrier=carrier)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    otel_context.attach(ctx)  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]

    span = trace.get_current_span(ctx)  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
    span_ctx = span.get_span_context()  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]

    if span_ctx and span_ctx.is_valid:  # pyright: ignore[reportUnknownMemberType]
        return {
            "trace_id": format(span_ctx.trace_id, "032x"),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            "span_id": format(span_ctx.span_id, "016x"),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            "trace_flags": format(span_ctx.trace_flags, "02x"),  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
            "tracestate": str(span_ctx.trace_state) if span_ctx.trace_state else "",  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        }

    # OTel didn't produce a valid context, fall back
    return _extract_context_manual(headers)


def _extract_context_manual(headers: list[tuple[bytes, bytes]]) -> dict[str, Any]:
    """Extract context using manual W3C traceparent/tracestate parsing."""
    traceparent_value: str | None = None
    tracestate_value: str = ""

    for key, value in headers:
        k = key.decode("latin-1").lower()
        if k == "traceparent":
            traceparent_value = value.decode("latin-1")
        elif k == "tracestate":
            tracestate_value = value.decode("latin-1")

    if traceparent_value is not None:
        parsed = _parse_traceparent(traceparent_value)
        if parsed is not None:
            # Valid traceparent — use trace_id from parent, generate new span_id
            return {
                "trace_id": parsed["trace_id"],
                "span_id": _generate_span_id(),
                "trace_flags": parsed["trace_flags"],
                "tracestate": _parse_tracestate(tracestate_value) if tracestate_value else "",
            }

    # No valid traceparent — generate new IDs
    return {
        "trace_id": _generate_trace_id(),
        "span_id": _generate_span_id(),
        "trace_flags": "01",
        "tracestate": "",
    }


def inject_context(
    headers: list[tuple[bytes, bytes]],
    trace_id: str,
    span_id: str,
    trace_flags: str = "01",
    tracestate: str = "",
) -> list[tuple[bytes, bytes]]:
    """Inject current trace context into outgoing response headers.

    Adds traceparent (and optionally tracestate) headers to the response.
    """
    # Try OTel propagation first
    if is_otel_available():
        try:
            return _inject_context_otel(headers)
        except Exception:
            _logger.debug("OTel context injection failed, falling back to manual", exc_info=True)

    return _inject_context_manual(headers, trace_id, span_id, trace_flags, tracestate)


def _inject_context_otel(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Inject context using OpenTelemetry propagation API."""
    from opentelemetry.context.propagation import get_global_textmap  # noqa: I001  # pyright: ignore[reportMissingImports,reportUnknownVariableType]

    carrier: dict[str, str] = {}
    propagator = get_global_textmap()  # pyright: ignore[reportUnknownVariableType]
    propagator.inject(carrier=carrier)  # pyright: ignore[reportUnknownMemberType]

    result = list(headers)
    for k, v in carrier.items():
        result.append((k.encode("latin-1"), v.encode("latin-1")))
    return result


def _inject_context_manual(
    headers: list[tuple[bytes, bytes]],
    trace_id: str,
    span_id: str,
    trace_flags: str = "01",
    tracestate: str = "",
) -> list[tuple[bytes, bytes]]:
    """Inject context using manual traceparent/tracestate header construction."""
    result = list(headers)

    traceparent = f"00-{trace_id}-{span_id}-{trace_flags}"
    result.append((b"traceparent", traceparent.encode("latin-1")))

    if tracestate:
        result.append((b"tracestate", tracestate.encode("latin-1")))

    return result
