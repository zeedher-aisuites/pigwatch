"""Real M2 simulator -> MQTT -> ingestion -> PostgreSQL -> API acceptance tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from pigwatch_api.main import create_app
from pigwatch_api.runtime import DependencyReadiness
from pigwatch_schemas import ObservationEnvelopeV1, PayloadType, SourceDelivery, SourceOrigin
from pigwatch_simulation import (
    EnvironmentalMeasurement,
    EnvironmentalSensorConfig,
    EnvironmentalSensorSimulator,
    MultiSourceSimulatorRunner,
    SimulationMode,
    SimulatorState,
)
from pigwatch_telemetry import (
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
    PostgresObservationRepository,
    ScopeKind,
    TelemetryProcessor,
    TopicRoute,
)
from tests.integration.test_10_telemetry_path import compose, wait_until

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "simulation" / "temperature-sequence.json"


class FixedClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        del seconds
        await stop_requested.wait()


class FiniteAdvancingClock:
    """Advance deterministic time and stop a periodic source after N readings."""

    def __init__(self, start: datetime, *, readings: int) -> None:
        self.current = start
        self.readings = readings
        self.wait_count = 0

    def now(self) -> datetime:
        return self.current

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        self.wait_count += 1
        self.current += timedelta(seconds=seconds)
        if self.wait_count >= self.readings:
            stop_requested.set()
        await asyncio.sleep(0)


class RecordingMqttPublisher:
    """Record simulator output while delegating every operation to the real M1 publisher."""

    def __init__(self, inner: MqttTelemetryPublisher) -> None:
        self.inner = inner
        self.calls: list[tuple[TopicRoute, ObservationEnvelopeV1]] = []

    async def start(self) -> None:
        await self.inner.start()

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        self.calls.append((route, envelope))
        await self.inner.publish(route, envelope)

    async def close(self) -> None:
        await self.inner.close()


@dataclass
class RetrievalRuntime:
    """Expose a real integration repository through the existing API routes."""

    repository: PostgresObservationRepository

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> DependencyReadiness:
        return DependencyReadiness(postgresql=True, mqtt=True)


def config_for(
    source_id: str,
    measurement: EnvironmentalMeasurement,
    *,
    seed: int,
    mode: SimulationMode = SimulationMode.STATIC,
    cadence_seconds: float = 1.0,
) -> EnvironmentalSensorConfig:
    values = {
        EnvironmentalMeasurement.TEMPERATURE: (22.0, 10.0, 35.0, 0.5),
        EnvironmentalMeasurement.RELATIVE_HUMIDITY: (60.0, 0.0, 100.0, 1.5),
        EnvironmentalMeasurement.NH3: (8.0, 0.0, 50.0, 0.75),
    }[measurement]
    initial, minimum, maximum, step = values
    return EnvironmentalSensorConfig(
        source_id=source_id,
        measurement=measurement,
        mode=mode,
        cadence_seconds=cadence_seconds,
        initial_value=initial,
        minimum_value=minimum,
        maximum_value=maximum,
        maximum_step=step,
        seed=seed,
        scope_kind=ScopeKind.SITE,
        scope_id="m2-integration-site",
    )


async def start_worker(
    repository: PostgresObservationRepository,
    settings: MqttConnectionSettings,
) -> MqttIngestionWorker:
    worker = MqttIngestionWorker(
        settings,
        TelemetryProcessor(repository),
        client_id=f"m2-integration-consumer-{uuid4()}",
    )
    await worker.start()
    assert await worker.wait_until_ready(10)
    return worker


async def retrieve(
    repository: PostgresObservationRepository,
    path: str,
) -> tuple[int, dict[str, Any]]:
    app = create_app(lambda: RetrievalRuntime(repository))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
    return response.status_code, response.json()


async def all_persisted(
    repository: PostgresObservationRepository,
    envelopes: list[ObservationEnvelopeV1],
) -> bool:
    return all([await repository.get(envelope.event_id) is not None for envelope in envelopes])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_three_environment_sources_complete_real_path_and_api_retrieval(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    event_time = datetime(2026, 9, 4, 12, tzinfo=UTC)
    worker = await start_worker(postgres_repository, mqtt_settings)
    real_publisher = MqttTelemetryPublisher(
        mqtt_settings,
        client_id=f"m2-integration-publisher-{uuid4()}",
    )
    publisher = RecordingMqttPublisher(real_publisher)
    sources = tuple(
        EnvironmentalSensorSimulator(configuration, clock=FixedClock(event_time))
        for configuration in (
            config_for("m2-temperature", EnvironmentalMeasurement.TEMPERATURE, seed=101),
            config_for("m2-humidity", EnvironmentalMeasurement.RELATIVE_HUMIDITY, seed=202),
            config_for("m2-nh3", EnvironmentalMeasurement.NH3, seed=303),
        )
    )
    try:
        await MultiSourceSimulatorRunner(sources, publisher).run()
        envelopes = [envelope for _, envelope in publisher.calls]
        await wait_until(lambda: all_persisted(postgres_repository, envelopes))

        assert len(envelopes) == 3
        assert {envelope.payload_type for envelope in envelopes} == {
            PayloadType.ENVIRONMENT_TEMPERATURE,
            PayloadType.ENVIRONMENT_RELATIVE_HUMIDITY,
            PayloadType.ENVIRONMENT_AMMONIA_CONCENTRATION,
        }
        assert {envelope.payload.unit for envelope in envelopes} == {"Cel", "%", "[ppm]"}
        assert all(envelope.source.origin is SourceOrigin.SYNTHETIC for envelope in envelopes)
        assert all(envelope.source.delivery is SourceDelivery.LIVE for envelope in envelopes)
        assert all(envelope.replay_time is None for envelope in envelopes)
        assert all(envelope.ingest_time is None for envelope in envelopes)

        for envelope in envelopes:
            stored = await postgres_repository.get(envelope.event_id)
            assert stored is not None
            assert stored.envelope.source.source_id == envelope.source.source_id
            assert stored.envelope.event_time == event_time
            assert stored.envelope.payload == envelope.payload
            assert stored.envelope.ingest_time is not None
            assert stored.envelope.ingest_time != stored.envelope.event_time

            status, body = await retrieve(
                postgres_repository,
                f"/v1/observations/{envelope.event_id}",
            )
            assert status == 200
            assert body["envelope"]["source"]["source_id"] == envelope.source.source_id
            assert body["envelope"]["payload"]["unit"] == envelope.payload.unit
    finally:
        await worker.close()

    assert all(source.state is SimulatorState.STOPPED for source in sources)
    assert all(source.task is not None and source.task.done() for source in sources)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_periodic_deterministic_sequence_survives_real_path(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    start = datetime.fromisoformat(fixture["start_time"].replace("Z", "+00:00"))
    configuration = config_for(
        fixture["source_id"],
        EnvironmentalMeasurement.TEMPERATURE,
        seed=fixture["seed"],
        mode=SimulationMode.PERIODIC,
        cadence_seconds=fixture["cadence_seconds"],
    ).model_copy(
        update={
            "initial_value": 22.0,
            "minimum_value": 21.0,
            "maximum_value": 23.0,
            "maximum_step": 0.4,
        }
    )
    worker = await start_worker(postgres_repository, mqtt_settings)
    publisher = RecordingMqttPublisher(
        MqttTelemetryPublisher(
            mqtt_settings,
            client_id=f"m2-deterministic-publisher-{uuid4()}",
        )
    )
    source = EnvironmentalSensorSimulator(
        configuration,
        clock=FiniteAdvancingClock(start, readings=3),
    )
    try:
        await MultiSourceSimulatorRunner((source,), publisher).run()
        envelopes = [envelope for _, envelope in publisher.calls]
        await wait_until(lambda: all_persisted(postgres_repository, envelopes))

        assert [envelope.payload.value for envelope in envelopes] == fixture["values"]
        assert [envelope.event_time for envelope in envelopes] == [
            start,
            start + timedelta(seconds=fixture["cadence_seconds"]),
            start + timedelta(seconds=fixture["cadence_seconds"] * 2),
        ]
        assert len({envelope.event_id for envelope in envelopes}) == 3
        for envelope in envelopes:
            assert await postgres_repository.count(envelope.event_id) == 1
    finally:
        await worker.close()

    assert source.state is SimulatorState.STOPPED
    assert source.task is not None and source.task.done()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_temporary_mqtt_outage_recovers_same_event_without_duplicate_row(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    worker = await start_worker(postgres_repository, mqtt_settings)
    publisher = MqttTelemetryPublisher(
        mqtt_settings,
        client_id=f"m2-recovery-publisher-{uuid4()}",
    )
    source = EnvironmentalSensorSimulator(
        config_for("m2-recovery-temperature", EnvironmentalMeasurement.TEMPERATURE, seed=404),
        clock=FixedClock(datetime(2026, 9, 4, 13, tzinfo=UTC)),
    )
    await source.open()
    envelope = source.next_observation()
    await publisher.start()
    assert await publisher.wait_until_connected(10)
    try:
        await asyncio.to_thread(compose, "stop", "mqtt")
        await wait_until(lambda: not worker.is_connected)
        await wait_until(lambda: not publisher.is_connected)

        publish_task = asyncio.create_task(publisher.publish(source.route, envelope))
        await asyncio.sleep(0.25)
        assert not publish_task.done()

        await asyncio.to_thread(compose, "start", "mqtt")
        await wait_until(lambda: worker.is_ready, timeout=30)
        await wait_until(lambda: publisher.is_connected, timeout=30)
        await asyncio.wait_for(publish_task, timeout=30)
        await wait_until(lambda: all_persisted(postgres_repository, [envelope]), timeout=30)

        # Repeat the same immutable generated event to exercise M1's topic-aware idempotency.
        await publisher.publish(source.route, envelope)
        await asyncio.sleep(0.5)
        assert await postgres_repository.count(envelope.event_id) == 1
    finally:
        await asyncio.to_thread(compose, "start", "mqtt")
        await source.close()
        await publisher.close()
        await worker.close()

    assert source.state is SimulatorState.STOPPED
