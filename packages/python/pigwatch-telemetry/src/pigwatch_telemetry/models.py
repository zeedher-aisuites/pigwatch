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


class RejectionCode(StrEnum):
    """Stable machine-readable invalid-message outcomes."""

    MESSAGE_TOO_LARGE = "MESSAGE_TOO_LARGE"
    MALFORMED_JSON = "MALFORMED_JSON"
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
        super().__init__(detail)
        self.code = code
        self.detail = detail[:512]
        self.event_id_text = event_id_text


class PersistenceUnavailable(RuntimeError):
    """Raised when PostgreSQL cannot durably complete a telemetry operation."""


class BrokerUnavailable(RuntimeError):
    """Raised when MQTT publication cannot receive broker acknowledgement."""
