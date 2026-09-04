"""Strict decoding and topic taxonomy tests for M1 telemetry."""

import json
from copy import deepcopy
from typing import Any

import pytest

from pigwatch_schemas import PayloadType, SourceDelivery, SourceOrigin, serialize_observation
from pigwatch_telemetry import (
    ObservationCategory,
    RejectionCode,
    ScopeKind,
    TelemetryValidationError,
    TopicRoute,
    decode_observation,
    parse_observation_topic,
)
from tests.support import load_observation_fixture


def fixture_data() -> dict[str, object]:
    return load_observation_fixture("synthetic-recorded").model_dump(mode="json")


def assert_rejected(data: object, expected: RejectionCode) -> None:
    raw = json.dumps(data, separators=(",", ":")).encode()
    with pytest.raises(TelemetryValidationError) as raised:
        decode_observation(raw)
    assert raised.value.code is expected


def test_all_static_provenance_fixtures_decode_without_losing_dimensions() -> None:
    expected = {
        "synthetic-live": (SourceOrigin.SYNTHETIC, SourceDelivery.LIVE),
        "synthetic-recorded": (SourceOrigin.SYNTHETIC, SourceDelivery.RECORDED),
        "physical-live": (SourceOrigin.PHYSICAL, SourceDelivery.LIVE),
        "physical-recorded": (SourceOrigin.PHYSICAL, SourceDelivery.RECORDED),
    }

    for name, provenance in expected.items():
        fixture = load_observation_fixture(name)
        decoded = decode_observation(serialize_observation(fixture))
        assert (decoded.source.origin, decoded.source.delivery) == provenance


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda data: data.pop("event_id"), RejectionCode.MISSING_EVENT_ID),
        (lambda data: data.update(event_id="invalid"), RejectionCode.INVALID_EVENT_ID),
        (
            lambda data: data.update(event_id="6ba7b810-9dad-41d1-80b4-00c04fd430c8"),
            RejectionCode.INVALID_EVENT_ID,
        ),
        (lambda data: data.pop("schema_version"), RejectionCode.MISSING_SCHEMA_VERSION),
        (
            lambda data: data.update(schema_version="99.0"),
            RejectionCode.UNSUPPORTED_SCHEMA_VERSION,
        ),
        (lambda data: data.pop("source"), RejectionCode.MISSING_PROVENANCE),
        (
            lambda data: data["source"].update(origin="UNKNOWN"),
            RejectionCode.INVALID_ORIGIN,
        ),
        (
            lambda data: data["source"].update(delivery="UNKNOWN"),
            RejectionCode.INVALID_DELIVERY,
        ),
        (lambda data: data.pop("event_time"), RejectionCode.MISSING_TIMESTAMP),
        (lambda data: data.pop("replay_time"), RejectionCode.MISSING_TIMESTAMP),
        (
            lambda data: data.update(event_time="not-a-time"),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            lambda data: data.update(replay_time="2026-09-02T15:30:00"),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            lambda data: data["source"].update(delivery="LIVE"),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            lambda data: data.update(event_time="2026-09-02T12:00:00"),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            lambda data: data.update(ingest_time="2026-09-02T12:00:00Z"),
            RejectionCode.PRODUCER_INGEST_TIME,
        ),
        (
            lambda data: data.update(payload_type="unknown"),
            RejectionCode.UNKNOWN_PAYLOAD_TYPE,
        ),
        (lambda data: data["payload"].pop("unit"), RejectionCode.INVALID_UNIT),
        (lambda data: data["payload"].update(unit="ratio"), RejectionCode.INVALID_UNIT),
        (lambda data: data["payload"].update(value="64"), RejectionCode.INVALID_VALUE),
        (lambda data: data.update(payload=[]), RejectionCode.STRUCTURALLY_INVALID),
    ],
)
def test_invalid_fields_receive_explicit_rejection_codes(
    mutation: object,
    expected: RejectionCode,
) -> None:
    data = deepcopy(fixture_data())
    callable_mutation = mutation
    assert callable(callable_mutation)
    callable_mutation(data)
    assert_rejected(data, expected)


@pytest.mark.parametrize(
    ("field_name", "mutation", "expected"),
    [
        (
            "schema_version",
            lambda data: data.update(schema_version={}),
            RejectionCode.UNSUPPORTED_SCHEMA_VERSION,
        ),
        ("source", lambda data: data.update(source=[]), RejectionCode.MISSING_PROVENANCE),
        (
            "source.origin",
            lambda data: data["source"].update(origin=[]),
            RejectionCode.INVALID_ORIGIN,
        ),
        (
            "source.delivery",
            lambda data: data["source"].update(delivery={}),
            RejectionCode.INVALID_DELIVERY,
        ),
        (
            "event_id",
            lambda data: data.update(event_id=[]),
            RejectionCode.INVALID_EVENT_ID,
        ),
        (
            "event_time",
            lambda data: data.update(event_time={}),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            "replay_time",
            lambda data: data.update(replay_time=[]),
            RejectionCode.INVALID_TIMESTAMP,
        ),
        (
            "payload_type",
            lambda data: data.update(payload_type={}),
            RejectionCode.UNKNOWN_PAYLOAD_TYPE,
        ),
        ("payload", lambda data: data.update(payload=[]), RejectionCode.STRUCTURALLY_INVALID),
        (
            "payload.value",
            lambda data: data["payload"].update(value={}),
            RejectionCode.INVALID_VALUE,
        ),
        (
            "payload.unit",
            lambda data: data["payload"].update(unit=[]),
            RejectionCode.INVALID_UNIT,
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_container_valued_fields_are_always_controlled_rejections(
    field_name: str,
    mutation: Any,
    expected: RejectionCode,
) -> None:
    data = deepcopy(fixture_data())
    assert callable(mutation), field_name
    mutation(data)

    assert_rejected(data, expected)


@pytest.mark.parametrize("raw", [b"{", b"\xff", b"null", b"[]"])
def test_malformed_or_non_object_json_rejects_explicitly(raw: bytes) -> None:
    expected = (
        RejectionCode.MALFORMED_JSON
        if raw in {b"{", b"\xff"}
        else RejectionCode.STRUCTURALLY_INVALID
    )
    with pytest.raises(TelemetryValidationError) as raised:
        decode_observation(raw)
    assert raised.value.code is expected


def test_oversized_message_rejects_before_parsing() -> None:
    with pytest.raises(TelemetryValidationError) as raised:
        decode_observation(b"x" * 65_537)
    assert raised.value.code is RejectionCode.MESSAGE_TOO_LARGE


@pytest.mark.parametrize(
    "raw",
    [
        b"[" * 10_000 + b"0" + b"]" * 10_000,
        b'{"":' * 10_000 + b"0" + b"}" * 10_000,
    ],
    ids=["arrays", "objects"],
)
def test_excessive_json_nesting_is_a_controlled_rejection(raw: bytes) -> None:
    assert len(raw) <= 65_536

    with pytest.raises(TelemetryValidationError) as raised:
        decode_observation(raw)

    assert raised.value.code is RejectionCode.JSON_NESTING_TOO_DEEP


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ('"schema_version":"1.0"', '"schema_version":"1.0","schema_version":"1.0"'),
        ('"origin":"SYNTHETIC"', '"origin":"SYNTHETIC","origin":"PHYSICAL"'),
        ('"value":64.0', '"value":64.0,"value":65.0'),
        ('"status":"UNCERTAIN"', '"status":"UNCERTAIN","status":"GOOD"'),
        (
            '"trace_id":"7f3f55a4443f48e48a63723c23c1276f"',
            '"trace_id":"7f3f55a4443f48e48a63723c23c1276f","trace_id":null',
        ),
    ],
)
def test_duplicate_json_keys_reject_recursively(needle: str, replacement: str) -> None:
    raw = serialize_observation(load_observation_fixture("synthetic-recorded"))
    duplicated = raw.decode().replace(needle, replacement, 1).encode()

    with pytest.raises(TelemetryValidationError) as raised:
        decode_observation(duplicated)

    assert raised.value.code is RejectionCode.DUPLICATE_JSON_KEY


def test_topic_round_trip_and_semantic_shape() -> None:
    route = TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="north-barn",
        source_id="fixture-synthetic-recorded",
        category=ObservationCategory.RELATIVE_HUMIDITY,
    )

    assert route.topic() == (
        "pigwatch/v1/observations/site/north-barn/fixture-synthetic-recorded/relative-humidity"
    )
    assert parse_observation_topic(route.topic()) == route


@pytest.mark.parametrize(
    "topic",
    [
        "pigwatch/v2/observations/site/north/source/temperature",
        "pigwatch/v1/observations/unknown/north/source/temperature",
        "pigwatch/v1/observations/site/NORTH/source/temperature",
        "pigwatch/v1/observations/site/north/source",
    ],
)
def test_invalid_topics_are_rejected(topic: str) -> None:
    with pytest.raises(TelemetryValidationError) as raised:
        parse_observation_topic(topic)
    assert raised.value.code is RejectionCode.TOPIC_MISMATCH


def test_payload_enum_contains_only_m1_static_contract_categories() -> None:
    assert [item.value for item in PayloadType] == [
        "environment.temperature",
        "environment.relative_humidity",
        "environment.ammonia_concentration",
    ]
