"""Strict MQTT wire-message decoding and rejection classification."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from pigwatch_schemas import (
    SCHEMA_VERSION_V1,
    ObservationEnvelopeV1,
    PayloadType,
    SourceDelivery,
    SourceOrigin,
)
from pigwatch_telemetry.models import (
    MAX_MESSAGE_BYTES,
    RejectionCode,
    TelemetryValidationError,
)


def _event_id_text(data: dict[str, Any]) -> str | None:
    value = data.get("event_id")
    return value if isinstance(value, str) else None


def _prevalidate(data: dict[str, Any]) -> str | None:
    event_id_text = _event_id_text(data)
    if "event_id" not in data:
        raise TelemetryValidationError(RejectionCode.MISSING_EVENT_ID, "event_id is required")
    try:
        event_id = UUID(str(data["event_id"]))
        if event_id.version != 7:
            raise ValueError
    except (TypeError, ValueError, AttributeError) as exc:
        raise TelemetryValidationError(
            RejectionCode.INVALID_EVENT_ID,
            "event_id must be an RFC 9562 UUIDv7",
            event_id_text=event_id_text,
        ) from exc

    if "schema_version" not in data:
        raise TelemetryValidationError(
            RejectionCode.MISSING_SCHEMA_VERSION,
            "schema_version is required",
            event_id_text=event_id_text,
        )
    if data["schema_version"] != SCHEMA_VERSION_V1:
        raise TelemetryValidationError(
            RejectionCode.UNSUPPORTED_SCHEMA_VERSION,
            f"unsupported schema_version: {data['schema_version']!r}",
            event_id_text=event_id_text,
        )

    source = data.get("source")
    if not isinstance(source, dict) or "origin" not in source or "delivery" not in source:
        raise TelemetryValidationError(
            RejectionCode.MISSING_PROVENANCE,
            "source origin and delivery are required",
            event_id_text=event_id_text,
        )
    if source["origin"] not in {item.value for item in SourceOrigin}:
        raise TelemetryValidationError(
            RejectionCode.INVALID_ORIGIN,
            "source origin is invalid",
            event_id_text=event_id_text,
        )
    if source["delivery"] not in {item.value for item in SourceDelivery}:
        raise TelemetryValidationError(
            RejectionCode.INVALID_DELIVERY,
            "source delivery is invalid",
            event_id_text=event_id_text,
        )

    if "event_time" not in data or "ingest_time" not in data:
        raise TelemetryValidationError(
            RejectionCode.MISSING_TIMESTAMP,
            "event_time and ingest_time are required",
            event_id_text=event_id_text,
        )
    if data["ingest_time"] is not None:
        raise TelemetryValidationError(
            RejectionCode.PRODUCER_INGEST_TIME,
            "wire ingest_time must be null",
            event_id_text=event_id_text,
        )

    payload_type = data.get("payload_type")
    if payload_type not in {item.value for item in PayloadType}:
        raise TelemetryValidationError(
            RejectionCode.UNKNOWN_PAYLOAD_TYPE,
            "payload_type is unknown",
            event_id_text=event_id_text,
        )
    payload = data.get("payload")
    if isinstance(payload, dict) and "unit" not in payload:
        raise TelemetryValidationError(
            RejectionCode.INVALID_UNIT,
            "payload unit is required",
            event_id_text=event_id_text,
        )
    return event_id_text


def _classify_validation_error(exc: ValidationError) -> RejectionCode:
    first = exc.errors(include_url=False)[0]
    location = tuple(str(part) for part in first["loc"])
    if first["type"] == "missing":
        return RejectionCode.STRUCTURALLY_INVALID
    if "event_time" in location or "ingest_time" in location:
        return RejectionCode.INVALID_TIMESTAMP
    if "unit" in location:
        return RejectionCode.INVALID_UNIT
    if "value" in location:
        return RejectionCode.INVALID_VALUE
    return RejectionCode.STRUCTURALLY_INVALID


def decode_observation(raw_message: bytes) -> ObservationEnvelopeV1:
    """Decode a strict supported wire envelope with explicit rejection reasons."""

    if len(raw_message) > MAX_MESSAGE_BYTES:
        raise TelemetryValidationError(
            RejectionCode.MESSAGE_TOO_LARGE,
            f"message exceeds {MAX_MESSAGE_BYTES} bytes",
        )
    try:
        decoded = json.loads(raw_message)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TelemetryValidationError(
            RejectionCode.MALFORMED_JSON,
            "message is not valid UTF-8 JSON",
        ) from exc
    if not isinstance(decoded, dict):
        raise TelemetryValidationError(
            RejectionCode.STRUCTURALLY_INVALID,
            "observation envelope must be a JSON object",
        )

    event_id_text = _prevalidate(decoded)
    try:
        # JSON strict mode accepts canonical JSON strings for UUID/datetime/enum fields while still
        # rejecting dangerous Python-side coercions such as numeric strings and booleans.
        return ObservationEnvelopeV1.model_validate_json(raw_message, strict=True)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        location = ".".join(str(part) for part in first["loc"])
        raise TelemetryValidationError(
            _classify_validation_error(exc),
            f"invalid field {location}: {first['msg']}",
            event_id_text=event_id_text,
        ) from exc
