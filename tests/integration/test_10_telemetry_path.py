"""Actual MQTT -> ingestion -> PostgreSQL -> retrieval integration tests."""

from __future__ import annotations

import asyncio
import os
import subprocess
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import CallbackAPIVersion

from pigwatch_schemas import ObservationEnvelopeV1, new_event_id
from pigwatch_telemetry import (
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
    ObservationCategory,
    PostgresObservationRepository,
    RejectionCode,
    ScopeKind,
    TelemetryProcessor,
    TopicRoute,
)
from tests.support import load_observation_fixture

REPOSITORY_ROOT = Path(__file__).parents[2]


def route_for(envelope: ObservationEnvelopeV1) -> TopicRoute:
    category = {
        "environment.temperature": ObservationCategory.TEMPERATURE,
        "environment.relative_humidity": ObservationCategory.RELATIVE_HUMIDITY,
        "environment.ammonia_concentration": ObservationCategory.AMMONIA_CONCENTRATION,
    }[envelope.payload_type.value]
    return TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="integration-site",
        source_id=envelope.source.source_id,
        category=category,
    )


async def wait_until(
    predicate: Callable[[], bool | Coroutine[Any, Any, bool]],
    *,
    timeout: float = 20,
) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        await asyncio.sleep(0.1)
    raise AssertionError("condition did not become true before timeout")


async def start_path(
    repository: PostgresObservationRepository,
    settings: MqttConnectionSettings,
    *,
    consumer_id: str,
) -> tuple[MqttIngestionWorker, MqttTelemetryPublisher]:
    worker = MqttIngestionWorker(
        settings,
        TelemetryProcessor(repository),
        client_id=consumer_id,
    )
    publisher = MqttTelemetryPublisher(
        settings,
        client_id=f"integration-publisher-{uuid4()}",
    )
    await worker.start()
    await publisher.start()
    assert await worker.wait_until_connected(10)
    assert await publisher.wait_until_connected(10)
    return worker, publisher


def publish_raw(settings: MqttConnectionSettings, topic: str, payload: bytes) -> None:
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=f"integration-raw-{uuid4()}",
        protocol=mqtt.MQTTv5,
    )
    client.connect(settings.host, settings.port, settings.keepalive_seconds, clean_start=True)
    client.loop_start()
    try:
        info = client.publish(topic, payload, qos=1, retain=False)
        info.wait_for_publish(10)
        assert info.is_published()
    finally:
        client.disconnect()
        client.loop_stop()


def compose(*arguments: str) -> None:
    project = os.environ.get("PIGWATCH_TEST_COMPOSE_PROJECT", "pigwatch-m1-integration")
    subprocess.run(
        ["docker", "compose", "-p", project, *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_provenance_combinations_round_trip_and_duplicate_is_idempotent(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker, publisher = await start_path(
        postgres_repository,
        mqtt_settings,
        consumer_id=f"integration-provenance-{uuid4()}",
    )
    fixture_names = (
        "synthetic-live",
        "synthetic-recorded",
        "physical-live",
        "physical-recorded",
    )
    envelopes = [load_observation_fixture(name) for name in fixture_names]
    try:
        for envelope in envelopes:
            await publisher.publish(route_for(envelope), envelope)
        await wait_until(
            lambda: _all_persisted(postgres_repository, [item.event_id for item in envelopes])
        )

        replay = envelopes[1]
        await publisher.publish(route_for(replay), replay)
        await publisher.publish(route_for(replay), replay)
        await asyncio.sleep(0.5)

        stored = [await postgres_repository.get(item.event_id) for item in envelopes]
        assert all(item is not None for item in stored)
        assert [
            (item.envelope.source.origin.value, item.envelope.source.delivery.value)
            for item in stored
            if item is not None
        ] == [
            ("SYNTHETIC", "LIVE"),
            ("SYNTHETIC", "RECORDED"),
            ("PHYSICAL", "LIVE"),
            ("PHYSICAL", "RECORDED"),
        ]
        assert await postgres_repository.count(replay.event_id) == 1
    finally:
        await publisher.close()
        await worker.close()


async def _all_persisted(
    repository: PostgresObservationRepository,
    event_ids: list[Any],
) -> bool:
    return all([await repository.get(event_id) is not None for event_id in event_ids])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_message_is_recorded_and_consumer_continues(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker, publisher = await start_path(
        postgres_repository,
        mqtt_settings,
        consumer_id=f"integration-invalid-{uuid4()}",
    )
    envelope = load_observation_fixture("synthetic-live")
    try:
        await asyncio.to_thread(publish_raw, mqtt_settings, route_for(envelope).topic(), b"{")
        await wait_until(lambda: _has_rejection(postgres_repository, RejectionCode.MALFORMED_JSON))

        await publisher.publish(route_for(envelope), envelope)
        await wait_until(lambda: _is_persisted(postgres_repository, envelope.event_id))

        assert worker.is_connected
        assert await postgres_repository.rejection_count(RejectionCode.MALFORMED_JSON) == 1
    finally:
        await publisher.close()
        await worker.close()


async def _has_rejection(
    repository: PostgresObservationRepository,
    code: RejectionCode,
) -> bool:
    return await repository.rejection_count(code) > 0


async def _is_persisted(repository: PostgresObservationRepository, event_id: Any) -> bool:
    return await repository.get(event_id) is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_persistent_session_delivers_message_after_consumer_restart(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    consumer_id = f"integration-restart-{uuid4()}"
    first_worker = MqttIngestionWorker(
        mqtt_settings,
        TelemetryProcessor(postgres_repository),
        client_id=consumer_id,
    )
    publisher = MqttTelemetryPublisher(
        mqtt_settings,
        client_id=f"integration-publisher-{uuid4()}",
    )
    envelope = load_observation_fixture("physical-recorded")
    await first_worker.start()
    await publisher.start()
    assert await first_worker.wait_until_connected(10)
    assert await publisher.wait_until_connected(10)
    await first_worker.close()

    await publisher.publish(route_for(envelope), envelope)
    await asyncio.sleep(0.5)
    assert await postgres_repository.get(envelope.event_id) is None

    second_worker = MqttIngestionWorker(
        mqtt_settings,
        TelemetryProcessor(postgres_repository),
        client_id=consumer_id,
    )
    try:
        await second_worker.start()
        assert await second_worker.wait_until_connected(10)
        await wait_until(lambda: _is_persisted(postgres_repository, envelope.event_id))
        assert await postgres_repository.count(envelope.event_id) == 1
    finally:
        await second_worker.close()
        await publisher.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_broker_restart_reconnects_and_processing_recovers(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker, publisher = await start_path(
        postgres_repository,
        mqtt_settings,
        consumer_id=f"integration-reconnect-{uuid4()}",
    )
    worker_connections = worker.connection_count
    publisher_connections = publisher.connection_count
    envelope = load_observation_fixture("physical-live").model_copy(
        update={"event_id": new_event_id()}
    )
    try:
        await asyncio.to_thread(compose, "restart", "mqtt")
        await wait_until(
            lambda: worker.connection_count > worker_connections and worker.is_connected,
            timeout=30,
        )
        await wait_until(
            lambda: publisher.connection_count > publisher_connections and publisher.is_connected,
            timeout=30,
        )
        await publisher.publish(route_for(envelope), envelope)
        await wait_until(lambda: _is_persisted(postgres_repository, envelope.event_id))
    finally:
        await publisher.close()
        await worker.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_database_outage_leaves_message_unacked_until_recovery(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker, publisher = await start_path(
        postgres_repository,
        mqtt_settings,
        consumer_id=f"integration-database-recovery-{uuid4()}",
    )
    envelope = load_observation_fixture("synthetic-live").model_copy(
        update={"event_id": new_event_id()}
    )
    try:
        await asyncio.to_thread(compose, "stop", "postgres")
        await wait_until(lambda: _database_unhealthy(postgres_repository), timeout=20)
        await publisher.publish(route_for(envelope), envelope)
        await asyncio.sleep(1.5)

        await asyncio.to_thread(compose, "start", "postgres")
        await wait_until(postgres_repository.healthcheck, timeout=30)
        await wait_until(lambda: _is_persisted(postgres_repository, envelope.event_id), timeout=30)
        assert await postgres_repository.count(envelope.event_id) == 1
    finally:
        await asyncio.to_thread(compose, "start", "postgres")
        await publisher.close()
        await worker.close()


async def _database_unhealthy(repository: PostgresObservationRepository) -> bool:
    return not await repository.healthcheck()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_out_of_order_arrival_queries_by_truthful_event_time(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker, publisher = await start_path(
        postgres_repository,
        mqtt_settings,
        consumer_id=f"integration-ordering-{uuid4()}",
    )
    base = load_observation_fixture("synthetic-live")
    earlier = base.model_copy(
        update={
            "event_id": new_event_id(),
            "event_time": datetime.now(UTC) - timedelta(hours=1),
        }
    )
    later = base.model_copy(
        update={
            "event_id": new_event_id(),
            "event_time": datetime.now(UTC) - timedelta(minutes=1),
        }
    )
    try:
        await publisher.publish(route_for(later), later)
        await publisher.publish(route_for(earlier), earlier)
        await wait_until(
            lambda: _all_persisted(postgres_repository, [earlier.event_id, later.event_id])
        )

        result = await postgres_repository.query(source_id=base.source.source_id, limit=10)
        assert [item.envelope.event_id for item in result] == [earlier.event_id, later.event_id]
        assert result[0].is_late is True
        assert result[0].envelope.ingest_time is not None
        assert result[1].envelope.ingest_time is not None
    finally:
        await publisher.close()
        await worker.close()
