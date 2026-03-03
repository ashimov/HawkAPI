"""Structured JSON logger for HawkAPI."""

from __future__ import annotations

import json
import logging
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON log formatter with request context fields."""

    _EXTRA_FIELDS = ("request_id", "method", "path", "status_code", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key in self._EXTRA_FIELDS:
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


def setup_structured_logging(level: str = "INFO") -> logging.Logger:
    """Configure the hawkapi logger with structured JSON output."""
    logger = logging.getLogger("hawkapi")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

    return logger
