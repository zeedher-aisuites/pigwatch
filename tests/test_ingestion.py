"""Behavior tests for normalization, idempotency, ordering and invalid evidence."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from pigwatch_schemas import ObservationEnvelopeV1, serialize_observation
from pigwatch_telemetry import (
    ObservationCategory,
    PersistenceUnavailable,
    ProcessingStatus,
    RejectionCode,
    ScopeKind,
    TelemetryProcessor,
    TopicRoute,
)
from tests.support import MemoryObservationRepository, load_observation_fixture

INGEST_TIME = datetime(2026, 9, 2, 16, tzinfo=UTC)


def route_for(envelope: ObservationEnvelopeV1) -> TopicRoute:
    category = {
        "environment.temperature": ObservationCategory.TEMPERATURE,
        "environment.relative_humidity": ObservationCategory.RELATIVE_HUMIDITY,
        "environment.ammonia_concentration": ObservationCategory.AMMONIA_CONCENTRATION,
    }[envelope.payload_type.value]
    return TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="test-site",
        source_id=envelope.source.source_id,
        category=category,
    )


@pytest.mark.asyncio
async def test_synthetic_recorded_provenance_survives_normalization() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-recorded")

    result = await processor.process(route_for(envelope).topic(), serialize_observation(envelope))
    stored = await repository.get(envelope.event_id)

    assert result.status is ProcessingStatus.ACCEPTED
    assert stored is not None
    assert stored.envelope.source.origin.value == "SYNTHETIC"
    assert stored.envelope.source.delivery.value == "RECORDED"
    assert stored.envelope.event_time == envelope.event_time
    assert stored.envelope.replay_time == envelope.replay_time
    assert stored.envelope.ingest_time == INGEST_TIME
    assert stored.is_late is True


@pytest.mark.asyncio
async def test_duplicate_is_idempotent_and_conflicting_content_rejects() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    topic = route_for(envelope).topic()
    raw = serialize_observation(envelope)

    first = await processor.process(topic, raw)
    duplicate = await processor.process(topic, raw)
    changed = envelope.model_copy(
        update={"payload": envelope.payload.model_copy(update={"value": 99.0})}
    )
    conflict = await processor.process(topic, serialize_observation(changed))

    assert first.status is ProcessingStatus.ACCEPTED
    assert duplicate.status is ProcessingStatus.DUPLICATE
    assert conflict.status is ProcessingStatus.REJECTED
    assert conflict.rejection_code is RejectionCode.EVENT_ID_CONFLICT
    assert len(repository.observations) == 1


@pytest.mark.asyncio
async def test_same_event_and_content_on_different_normalized_route_is_conflict() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    first_route = route_for(envelope)
    different_route = TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="different-site",
        source_id=envelope.source.source_id,
        category=first_route.category,
    )
    raw = serialize_observation(envelope)

    first = await processor.process(first_route.topic(), raw)
    conflict = await processor.process(different_route.topic(), raw)

    assert first.status is ProcessingStatus.ACCEPTED
    assert conflict.status is ProcessingStatus.REJECTED
    assert conflict.rejection_code is RejectionCode.EVENT_ID_CONFLICT
    assert len(repository.observations) == 1


@pytest.mark.asyncio
async def test_out_of_order_events_retain_times_and_query_in_event_order() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    earlier = load_observation_fixture("synthetic-live")
    later = load_observation_fixture("physical-live")
    assert earlier.event_time < later.event_time

    await processor.process(route_for(later).topic(), serialize_observation(later))
    await processor.process(route_for(earlier).topic(), serialize_observation(earlier))
    result = await repository.query(limit=10)

    assert [item.envelope.event_id for item in result] == [earlier.event_id, later.event_id]
    assert all(item.envelope.ingest_time == INGEST_TIME for item in result)


@pytest.mark.asyncio
async def test_future_event_is_truthful_and_flagged_for_clock_skew() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live").model_copy(
        update={"event_time": INGEST_TIME + timedelta(minutes=6)}
    )

    await processor.process(route_for(envelope).topic(), serialize_observation(envelope))
    stored = await repository.get(envelope.event_id)

    assert stored is not None
    assert stored.envelope.event_time == INGEST_TIME + timedelta(minutes=6)
    assert stored.clock_skew_detected is True


@pytest.mark.asyncio
async def test_invalid_message_is_recorded_and_processor_remains_healthy() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    topic = route_for(envelope).topic()

    invalid = await processor.process(topic, b"{")
    valid = await processor.process(topic, serialize_observation(envelope))

    assert invalid.status is ProcessingStatus.REJECTED
    assert invalid.rejection_code is RejectionCode.MALFORMED_JSON
    assert valid.status is ProcessingStatus.ACCEPTED
    assert len(repository.rejections) == 1


@pytest.mark.asyncio
async def test_oversized_rejection_retains_bounded_evidence_and_hash() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)

    result = await processor.process(
        "pigwatch/v1/observations/global/all/source/temperature",
        b"x" * 70_000,
    )

    assert result.rejection_code is RejectionCode.MESSAGE_TOO_LARGE
    assert len(repository.rejections[0].raw_message) == 65_536
    assert repository.rejections[0].raw_truncated is True
    assert len(repository.rejections[0].raw_sha256) == 64


@pytest.mark.asyncio
async def test_deep_json_rejection_retains_exact_bounded_evidence_and_hash() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    raw = b'{"":' * 10_000 + b"0" + b"}" * 10_000

    result = await processor.process(
        "pigwatch/v1/observations/global/all/source/temperature",
        raw,
    )

    assert result.status is ProcessingStatus.REJECTED
    assert result.rejection_code is RejectionCode.JSON_NESTING_TOO_DEEP
    assert len(repository.rejections) == 1
    assert repository.rejections[0].raw_message == raw
    assert len(repository.rejections[0].raw_message) <= 65_536
    assert repository.rejections[0].raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert repository.rejections[0].raw_truncated is False


@pytest.mark.asyncio
async def test_topic_mismatch_is_rejected_without_fabricating_identity() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    wrong_topic = TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="test-site",
        source_id="different-source",
        category=ObservationCategory.TEMPERATURE,
    ).topic()

    result = await processor.process(wrong_topic, serialize_observation(envelope))

    assert result.status is ProcessingStatus.REJECTED
    assert result.rejection_code is RejectionCode.TOPIC_MISMATCH
    assert not repository.observations


@pytest.mark.asyncio
async def test_database_failure_is_visible_and_not_converted_to_rejection() -> None:
    repository = MemoryObservationRepository()
    repository.available = False
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")

    with pytest.raises(PersistenceUnavailable):
        await processor.process(route_for(envelope).topic(), serialize_observation(envelope))

    assert not repository.rejections


@pytest.mark.asyncio
async def test_structurally_invalid_payload_does_not_gain_defaults() -> None:
    repository = MemoryObservationRepository()
    processor = TelemetryProcessor(repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    data = envelope.model_dump(mode="json")
    del data["payload"]["value"]

    result = await processor.process(
        route_for(envelope).topic(),
        json.dumps(data).encode(),
    )

    assert result.rejection_code is RejectionCode.STRUCTURALLY_INVALID
    assert not repository.observations
