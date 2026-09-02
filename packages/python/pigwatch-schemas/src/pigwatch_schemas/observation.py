"""Versioned transport-neutral observation contracts for PigWatch telemetry."""

from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    UUID7,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    field_validator,
    model_validator,
)

from pigwatch_schemas.source import SourceDescriptor

SCHEMA_VERSION_V1: Final[Literal["1.0"]] = "1.0"

FiniteNumber = Annotated[StrictFloat, Field(allow_inf_nan=False)]


class PayloadType(StrEnum):
    """Typed payload discriminators supported by the M1 transport contract."""

    ENVIRONMENT_TEMPERATURE = "environment.temperature"
    ENVIRONMENT_RELATIVE_HUMIDITY = "environment.relative_humidity"
    ENVIRONMENT_AMMONIA_CONCENTRATION = "environment.ammonia_concentration"


class ObservationUnit(StrEnum):
    """Explicit unit codes accepted by the M1 scalar fixture payloads."""

    DEGREE_CELSIUS = "Cel"
    PERCENT = "%"
    PARTS_PER_MILLION = "[ppm]"


class QualityStatus(StrEnum):
    """Condition assigned to evidence by its reporting source."""

    GOOD = "GOOD"
    UNCERTAIN = "UNCERTAIN"
    BAD = "BAD"


class TemperaturePayload(BaseModel):
    """Static scalar temperature contract; acquisition behavior belongs to M2+."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: FiniteNumber
    unit: Literal["Cel"]


class RelativeHumidityPayload(BaseModel):
    """Static scalar relative-humidity contract; acquisition behavior belongs to M2+."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Annotated[StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)]
    unit: Literal["%"]


class AmmoniaConcentrationPayload(BaseModel):
    """Static scalar NH3 contract; acquisition behavior belongs to M2+."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]
    unit: Literal["[ppm]"]


ObservationPayload = TemperaturePayload | RelativeHumidityPayload | AmmoniaConcentrationPayload


class QualityMetadata(BaseModel):
    """Optional source-supplied evidence quality metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: QualityStatus
    confidence: Annotated[StrictFloat, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    flags: tuple[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")], ...] = ()


class TraceMetadata(BaseModel):
    """Optional identifiers for correlating evidence and operational traces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_id: UUID | None = None
    trace_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")] | None = None

    @model_validator(mode="after")
    def require_identifier(self) -> TraceMetadata:
        """Reject an empty trace object; callers should use null instead."""

        if self.correlation_id is None and self.trace_id is None:
            raise ValueError("trace metadata requires correlation_id or trace_id")
        return self


class ObservationEnvelopeV1(BaseModel):
    """Strict, versioned observation evidence envelope used on MQTT and in storage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID7
    schema_version: Literal["1.0"]
    source: SourceDescriptor
    event_time: AwareDatetime
    ingest_time: AwareDatetime | None
    payload_type: PayloadType
    payload: ObservationPayload
    quality: QualityMetadata | None
    trace: TraceMetadata | None

    @field_validator("event_time", "ingest_time")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        """Normalize accepted aware timestamps to UTC without changing their instant."""

        if value is None:
            return None
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_payload_discriminator(self) -> ObservationEnvelopeV1:
        """Require the top-level discriminator to match the typed payload."""

        expected_type: dict[PayloadType, type[BaseModel]] = {
            PayloadType.ENVIRONMENT_TEMPERATURE: TemperaturePayload,
            PayloadType.ENVIRONMENT_RELATIVE_HUMIDITY: RelativeHumidityPayload,
            PayloadType.ENVIRONMENT_AMMONIA_CONCENTRATION: AmmoniaConcentrationPayload,
        }
        if not isinstance(self.payload, expected_type[self.payload_type]):
            raise ValueError("payload does not match payload_type")
        return self

    def accepted_at(self, ingest_time: datetime) -> ObservationEnvelopeV1:
        """Return an immutable copy carrying PigWatch's authoritative ingest time."""

        if ingest_time.tzinfo is None or ingest_time.utcoffset() is None:
            raise ValueError("ingest_time must be timezone-aware")
        return self.model_copy(update={"ingest_time": ingest_time.astimezone(UTC)})


def serialize_observation(envelope: ObservationEnvelopeV1) -> bytes:
    """Serialize an observation as deterministic compact UTF-8 JSON."""

    data = envelope.model_dump(mode="json")
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()


def new_event_id(*, timestamp_ms: int | None = None, randomness: int | None = None) -> UUID:
    """Generate an RFC 9562 UUIDv7 using millisecond time and 74 random bits."""

    unix_ms = time.time_ns() // 1_000_000 if timestamp_ms is None else timestamp_ms
    if not 0 <= unix_ms < 1 << 48:
        raise ValueError("timestamp_ms must fit in 48 bits")

    random_bits = secrets.randbits(74) if randomness is None else randomness
    if not 0 <= random_bits < 1 << 74:
        raise ValueError("randomness must fit in 74 bits")

    random_a = random_bits >> 62
    random_b = random_bits & ((1 << 62) - 1)
    value = (unix_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return UUID(int=value)
