"""Contract tests for the versioned M1 observation envelope."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from pigwatch_schemas import (
    SCHEMA_VERSION_V1,
    ObservationEnvelopeV1,
    PayloadType,
    QualityMetadata,
    QualityStatus,
    SourceDelivery,
    SourceDescriptor,
    SourceOrigin,
    TemperaturePayload,
    TraceMetadata,
    new_event_id,
    serialize_observation,
)

EVENT_ID = UUID("019941c8-3800-7000-8000-000000000001")


def make_envelope() -> ObservationEnvelopeV1:
    """Build a static observation fixture without implementing a sensor."""

    return ObservationEnvelopeV1(
        event_id=EVENT_ID,
        schema_version=SCHEMA_VERSION_V1,
        source=SourceDescriptor(
            source_id="fixture-environment-1",
            origin=SourceOrigin.SYNTHETIC,
            delivery=SourceDelivery.RECORDED,
        ),
        event_time=datetime(2026, 9, 2, 12, tzinfo=UTC),
        ingest_time=None,
        payload_type=PayloadType.ENVIRONMENT_TEMPERATURE,
        payload=TemperaturePayload(value=21.5, unit="Cel"),
        quality=QualityMetadata(status=QualityStatus.GOOD, confidence=0.98),
        trace=TraceMetadata(
            correlation_id=UUID("019941c8-3800-7000-8000-000000000010"),
            trace_id="7f3f55a4443f48e48a63723c23c1276f",
        ),
    )


def test_envelope_serialization_is_deterministic_and_preserves_provenance() -> None:
    envelope = make_envelope()

    first = serialize_observation(envelope)
    second = serialize_observation(envelope)
    decoded = ObservationEnvelopeV1.model_validate_json(first, strict=True)

    assert first == second
    assert decoded == envelope
    assert decoded.source.origin is SourceOrigin.SYNTHETIC
    assert decoded.source.delivery is SourceDelivery.RECORDED
    assert decoded.ingest_time is None
    assert json.loads(first)["payload"]["unit"] == "Cel"


def test_ingest_time_is_authoritative_utc_copy() -> None:
    envelope = make_envelope()
    accepted = envelope.accepted_at(datetime(2026, 9, 2, 8, tzinfo=UTC) + timedelta(hours=4))

    assert envelope.ingest_time is None
    assert accepted.ingest_time == datetime(2026, 9, 2, 12, tzinfo=UTC)


def test_uuid7_generator_has_expected_version_and_is_deterministic_when_seeded() -> None:
    event_id = new_event_id(timestamp_ms=1_725_192_000_000, randomness=1)

    assert event_id.version == 7
    assert event_id.variant == "specified in RFC 4122"
    assert event_id == new_event_id(timestamp_ms=1_725_192_000_000, randomness=1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "not-a-uuid"),
        ("event_id", "6ba7b810-9dad-41d1-80b4-00c04fd430c8"),
        ("schema_version", "2.0"),
        ("event_time", "2026-09-02T12:00:00"),
    ],
)
def test_envelope_rejects_invalid_identity_version_and_time(field: str, value: str) -> None:
    data = make_envelope().model_dump(mode="json")
    data[field] = value

    with pytest.raises(ValidationError):
        ObservationEnvelopeV1.model_validate(data)


@pytest.mark.parametrize("value", ["21.5", True, float("nan"), float("inf")])
def test_temperature_rejects_ambiguous_or_non_finite_values(value: object) -> None:
    with pytest.raises(ValidationError):
        TemperaturePayload.model_validate({"value": value, "unit": "Cel"})


def test_payload_discriminator_and_unit_cannot_disagree() -> None:
    data = make_envelope().model_dump(mode="json")
    data["payload_type"] = PayloadType.ENVIRONMENT_RELATIVE_HUMIDITY

    with pytest.raises(ValidationError):
        ObservationEnvelopeV1.model_validate(data)

    with pytest.raises(ValidationError):
        TemperaturePayload.model_validate({"value": 21.5, "unit": "degF"})


def test_trace_metadata_rejects_empty_or_invalid_values() -> None:
    with pytest.raises(ValidationError):
        TraceMetadata()

    with pytest.raises(ValidationError):
        TraceMetadata(trace_id="not-hex")
