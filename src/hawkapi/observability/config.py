"""Observability configuration."""

from __future__ import annotations

from dataclasses import dataclass

_VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Configuration for the observability subsystem."""

    enable_tracing: bool = True
    enable_logging: bool = True
    enable_metrics: bool = True
    log_level: str = "INFO"
    log_format: str = "json"
    trace_sample_rate: float = 1.0
    service_name: str = "hawkapi"
    metrics_prefix: str = "hawkapi"
    request_id_header: str = "x-request-id"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.trace_sample_rate <= 1.0:
            msg = f"trace_sample_rate must be between 0.0 and 1.0, got {self.trace_sample_rate}"
            raise ValueError(msg)
        if self.log_level.upper() not in _VALID_LOG_LEVELS:
            msg = f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {self.log_level!r}"
            raise ValueError(msg)
        if not self.service_name:
            msg = "service_name must not be empty"
            raise ValueError(msg)
