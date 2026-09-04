"""Internal telemetry processing and persistence models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from pigwatch_schemas import ObservationEnvelopeV1

MAX_MESSAGE_BYTES = 65_536
LATE_THRESHOLD_SECONDS = 300
MAX_TOPIC_CHARS = 512
MAX_EVENT_ID_TEXT_CHARS = 128
MAX_ERROR_DETAIL_CHARS = 512


def sanitize_diagnostic_text(value: str, *, max_chars: int) -> str:
    """Bound diagnostic text and replace database/log-hostile code points deterministically."""

    return "".join(character if character.isprintable() else "�" for character in value[:max_chars])


class RejectionCode(StrEnum):
    """Stable machine-readable invalid-message outcomes."""

    MESSAGE_TOO_LARGE = "MESSAGE_TOO_LARGE"
    MALFORMED_JSON = "MALFORMED_JSON"
    JSON_NESTING_TOO_DEEP = "JSON_NESTING_TOO_DEEP"
    DUPLICATE_JSON_KEY = "DUPLICATE_JSON_KEY"
    STRUCTURALLY_INVALID = "STRUCTURALLY_INVALID"
    MISSING_EVENT_ID = "MISSING_EVENT_ID"
    INVALID_EVENT_ID = "INVALID_EVENT_ID"
    MISSING_SCHEMA_VERSION = "MISSING_SCHEMA_VERSION"
    UNSUPPORTED_SCHEMA_VERSION = "UNSUPPORTED_SCHEMA_VERSION"
    MISSING_PROVENANCE = "MISSING_PROVENANCE"
    INVALID_ORIGIN = "INVALID_ORIGIN"
    INVALID_DELIVERY = "INVALID_DELIVERY"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    PRODUCER_INGEST_TIME = "PRODUCER_INGEST_TIME"
    UNKNOWN_PAYLOAD_TYPE = "UNKNOWN_PAYLOAD_TYPE"
    INVALID_VALUE = "INVALID_VALUE"
    INVALID_UNIT = "INVALID_UNIT"
    TOPIC_MISMATCH = "TOPIC_MISMATCH"
    EVENT_ID_CONFLICT = "EVENT_ID_CONFLICT"


class ProcessingStatus(StrEnum):
    """Durable outcome of one MQTT delivery attempt."""

    ACCEPTED = "ACCEPTED"
    DUPLICATE = "DUPLICATE"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    """Outcome returned to the MQTT acknowledgement boundary."""

    status: ProcessingStatus
    event_id: UUID | None
    rejection_code: RejectionCode | None = None


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    """Validated observation plus transport and arrival metadata for persistence."""

    envelope: ObservationEnvelopeV1
    topic: str
    raw_message: bytes
    fingerprint: str
    is_late: bool
    clock_skew_detected: bool


@dataclass(frozen=True, slots=True)
class RejectionEvidence:
    """Bounded evidence retained when an MQTT message cannot be accepted."""

    received_at: datetime
    topic: str
    event_id_text: str | None
    code: RejectionCode
    detail: str
    raw_message: bytes
    raw_sha256: str
    raw_truncated: bool

    def __post_init__(self) -> None:
        """Make deterministic invalid input safe for bounded PostgreSQL columns."""

        object.__setattr__(
            self,
            "topic",
            sanitize_diagnostic_text(self.topic, max_chars=MAX_TOPIC_CHARS),
        )
        if self.event_id_text is not None:
            object.__setattr__(
                self,
                "event_id_text",
                sanitize_diagnostic_text(
                    self.event_id_text,
                    max_chars=MAX_EVENT_ID_TEXT_CHARS,
                ),
            )
        object.__setattr__(
            self,
            "detail",
            sanitize_diagnostic_text(self.detail, max_chars=MAX_ERROR_DETAIL_CHARS),
        )
        if len(self.raw_message) > MAX_MESSAGE_BYTES:
            object.__setattr__(self, "raw_message", self.raw_message[:MAX_MESSAGE_BYTES])
            object.__setattr__(self, "raw_truncated", True)


class StoredObservation(BaseModel):
    """Retrieval representation for one accepted durable observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    envelope: ObservationEnvelopeV1
    topic: str
    is_late: bool
    clock_skew_detected: bool
    processing_outcome: ProcessingStatus


class TelemetryValidationError(ValueError):
    """Expected validation failure with safe observable context."""

    def __init__(
        self,
        code: RejectionCode,
        detail: str,
        *,
        event_id_text: str | None = None,
    ) -> None:
        safe_detail = sanitize_diagnostic_text(detail, max_chars=MAX_ERROR_DETAIL_CHARS)
        super().__init__(safe_detail)
        self.code = code
        self.detail = safe_detail
        self.event_id_text = (
            sanitize_diagnostic_text(event_id_text, max_chars=MAX_EVENT_ID_TEXT_CHARS)
            if event_id_text is not None
            else None
        )


class PersistenceUnavailable(RuntimeError):
    """Raised when PostgreSQL cannot durably complete a telemetry operation."""


class BrokerUnavailable(RuntimeError):
    """Raised when MQTT publication cannot receive broker acknowledgement."""


class ShutdownTimeout(RuntimeError):
    """Raised when ingestion processing cannot settle before its shutdown deadline."""
