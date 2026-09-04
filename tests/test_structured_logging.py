"""Safety tests for structured telemetry logs."""

import json
import logging

from pigwatch_telemetry import JsonLogFormatter


def test_json_logging_includes_safe_context_and_excludes_raw_or_secrets() -> None:
    record = logging.LogRecord(
        name="pigwatch.telemetry",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="telemetry_processed",
        args=(),
        exc_info=None,
    )
    record.event_id = "019941c8-3800-7000-8000-000000000001"
    record.source_id = "fixture-synthetic-live"
    record.outcome = "ACCEPTED"
    record.failure_kind = "TimeoutError"
    record.measurement = "TEMPERATURE"
    record.mode = "PERIODIC"
    record.source_count = 3
    record.raw_message = b"secret-payload"
    record.database_url = "postgresql://user:password@example"

    formatted = JsonLogFormatter().format(record)
    decoded = json.loads(formatted)

    assert decoded["event"] == "telemetry_processed"
    assert decoded["event_id"] == "019941c8-3800-7000-8000-000000000001"
    assert decoded["source_id"] == "fixture-synthetic-live"
    assert decoded["outcome"] == "ACCEPTED"
    assert decoded["failure_kind"] == "TimeoutError"
    assert decoded["measurement"] == "TEMPERATURE"
    assert decoded["mode"] == "PERIODIC"
    assert decoded["source_count"] == "3"
    assert "raw_message" not in decoded
    assert "database_url" not in decoded
    assert "secret-payload" not in formatted
    assert "password" not in formatted
