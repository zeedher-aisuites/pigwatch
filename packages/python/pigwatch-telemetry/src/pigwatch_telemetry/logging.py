"""Pragmatic JSON logging without raw telemetry or secret values."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

SAFE_CONTEXT_FIELDS = (
    "event_id",
    "source_id",
    "topic",
    "outcome",
    "rejection_code",
    "broker_state",
    "dependency",
    "failure_kind",
    "retry_seconds",
)


class JsonLogFormatter(logging.Formatter):
    """Render one safe structured JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for field in SAFE_CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = str(value)
        if record.exc_info is not None:
            exception_type = record.exc_info[0]
            if exception_type is not None:
                payload["exception"] = exception_type.__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for safe single-line telemetry diagnostics."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
