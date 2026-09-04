"""Real PostgreSQL regressions for M1 review findings."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from typing import cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from pigwatch_schemas import new_event_id, serialize_observation
from pigwatch_telemetry import (
    ObservationCategory,
    PostgresObservationRepository,
    ProcessingStatus,
    RejectionCode,
    ScopeKind,
    TelemetryProcessor,
    TopicRoute,
    canonical_observation_fingerprint,
    telemetry_rejections,
)
from tests.support import load_observation_fixture

INGEST_TIME = datetime(2026, 9, 2, 16, tzinfo=UTC)


def topic(scope_id: str) -> str:
    return TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id=scope_id,
        source_id="fixture-synthetic-live",
        category=ObservationCategory.TEMPERATURE,
    ).topic()


async def rejection_rows(database_url: str) -> list[dict[str, object]]:
    engine = create_async_engine(database_url)
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                select(telemetry_rejections).order_by(telemetry_rejections.c.rejection_id)
            )
        ).mappings()
        result = [dict(row) for row in rows]
    await engine.dispose()
    return result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_concurrent_identical_duplicates_create_one_observation(
    postgres_repository: PostgresObservationRepository,
) -> None:
    envelope = load_observation_fixture("synthetic-live").model_copy(
        update={"event_id": new_event_id()}
    )
    processor = TelemetryProcessor(postgres_repository, clock=lambda: INGEST_TIME)
    raw = serialize_observation(envelope)

    results = await asyncio.gather(
        *(processor.process(topic("same-scope"), raw) for _ in range(12))
    )

    assert sum(result.status is ProcessingStatus.ACCEPTED for result in results) == 1
    assert sum(result.status is ProcessingStatus.DUPLICATE for result in results) == 11
    assert await postgres_repository.count(envelope.event_id) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_concurrent_content_and_routing_conflicts_are_explicit(
    postgres_repository: PostgresObservationRepository,
) -> None:
    envelope = load_observation_fixture("synthetic-live").model_copy(
        update={"event_id": new_event_id()}
    )
    changed = envelope.model_copy(
        update={"payload": envelope.payload.model_copy(update={"value": 99.0})}
    )
    processor = TelemetryProcessor(postgres_repository, clock=lambda: INGEST_TIME)

    results = await asyncio.gather(
        processor.process(topic("scope-a"), serialize_observation(envelope)),
        processor.process(topic("scope-a"), serialize_observation(changed)),
        processor.process(topic("scope-b"), serialize_observation(envelope)),
    )

    assert sum(result.status is ProcessingStatus.ACCEPTED for result in results) == 1
    assert sum(result.status is ProcessingStatus.REJECTED for result in results) == 2
    assert all(
        result.rejection_code is RejectionCode.EVENT_ID_CONFLICT
        for result in results
        if result.status is ProcessingStatus.REJECTED
    )
    assert await postgres_repository.count(envelope.event_id) == 1
    assert await postgres_repository.rejection_count(RejectionCode.EVENT_ID_CONFLICT) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_conflict_raw_hash_uses_exact_differently_formatted_message(
    postgres_repository: PostgresObservationRepository,
    integration_database_url: str,
) -> None:
    envelope = load_observation_fixture("synthetic-live").model_copy(
        update={"event_id": new_event_id()}
    )
    changed = envelope.model_copy(
        update={"payload": envelope.payload.model_copy(update={"value": 33.25})}
    )
    processor = TelemetryProcessor(postgres_repository, clock=lambda: INGEST_TIME)
    normalized_topic = topic("raw-hash")
    await processor.process(normalized_topic, serialize_observation(envelope))
    pretty_raw = json.dumps(
        changed.model_dump(mode="json"),
        indent=2,
        sort_keys=False,
    ).encode()

    conflict = await processor.process(normalized_topic, pretty_raw)
    rows = await rejection_rows(integration_database_url)

    assert conflict.rejection_code is RejectionCode.EVENT_ID_CONFLICT
    assert len(rows) == 1
    assert rows[0]["raw_message"] == pretty_raw
    assert rows[0]["raw_sha256"] == hashlib.sha256(pretty_raw).hexdigest()
    canonical_fingerprint = canonical_observation_fingerprint(
        topic=normalized_topic,
        envelope_bytes=serialize_observation(changed),
    )
    assert rows[0]["raw_sha256"] != canonical_fingerprint


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pathological_invalid_metadata_is_sanitized_bounded_and_durable(
    postgres_repository: PostgresObservationRepository,
    integration_database_url: str,
) -> None:
    processor = TelemetryProcessor(postgres_repository, clock=lambda: INGEST_TIME)
    envelope = load_observation_fixture("synthetic-live")
    valid_raw = serialize_observation(envelope)

    long_id_data = envelope.model_dump(mode="json")
    long_id_data["event_id"] = "x" * 2_000
    long_id_raw = json.dumps(long_id_data).encode()

    control_data = envelope.model_dump(mode="json")
    control_data["event_id"] = "bad\x00\n\tid"
    control_raw = json.dumps(control_data).encode()

    long_topic = "x" * 2_000 + "\x00\n\t"
    malformed_raw = b"{"
    oversized_raw = b"x" * 70_000
    inputs = (
        (topic("long-id"), long_id_raw),
        (topic("control-id"), control_raw),
        (long_topic, valid_raw),
        (topic("malformed"), malformed_raw),
        (topic("oversized"), oversized_raw),
    )

    results = []
    for input_topic, raw in inputs:
        results.append(await processor.process(input_topic, raw))

    rows = await rejection_rows(integration_database_url)
    assert all(result.status is ProcessingStatus.REJECTED for result in results)
    assert len(rows) == len(inputs)
    assert Counter(str(row["raw_sha256"]) for row in rows) == Counter(
        hashlib.sha256(raw).hexdigest() for _, raw in inputs
    )
    assert all(len(str(row["topic"])) <= 512 for row in rows)
    assert all(str(row["topic"]).isprintable() for row in rows)
    assert all(
        row["event_id_text"] is None or len(str(row["event_id_text"])) <= 128 for row in rows
    )
    assert all(
        row["event_id_text"] is None or str(row["event_id_text"]).isprintable() for row in rows
    )
    assert all(len(str(row["error_detail"])) <= 512 for row in rows)
    assert all(str(row["error_detail"]).isprintable() for row in rows)
    assert all(len(cast(bytes, row["raw_message"])) <= 65_536 for row in rows)

    oversized = next(row for row in rows if row["error_code"] == "MESSAGE_TOO_LARGE")
    assert oversized["raw_truncated"] is True
    assert len(cast(bytes, oversized["raw_message"])) == 65_536
    assert any(len(str(row["event_id_text"])) == 128 for row in rows if row["event_id_text"])
    assert any(len(str(row["topic"])) == 512 for row in rows)
