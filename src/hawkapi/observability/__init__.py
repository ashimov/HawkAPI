"""Observability subsystem — tracing, structured logs, metrics."""

from hawkapi.observability.config import ObservabilityConfig
from hawkapi.observability.middleware import ObservabilityMiddleware

__all__ = ["ObservabilityConfig", "ObservabilityMiddleware"]
