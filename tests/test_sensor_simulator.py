"""Behavior and contract tests for the deterministic M2 sensor simulator."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import MQTTErrorCode
from pydantic import ValidationError

from pigwatch_schemas import (
    AmmoniaConcentrationPayload,
    ObservationEnvelopeV1,
    RelativeHumidityPayload,
    SourceDelivery,
    SourceOrigin,
    TemperaturePayload,
    serialize_observation,
)
from pigwatch_simulation import (
    EnvironmentalMeasurement,
    EnvironmentalSensorConfig,
    EnvironmentalSensorSimulator,
    MultiSourceSimulatorRunner,
    SimulationMode,
    SimulatorConfiguration,
    SimulatorState,
)
from pigwatch_sources import SourceLifecycle
from pigwatch_telemetry import (
    BrokerUnavailable,
    MqttConnectionSettings,
    MqttTelemetryPublisher,
    ScopeKind,
    TopicRoute,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
FIXED_TIME = datetime(2026, 9, 4, 12, tzinfo=UTC)


def sensor_config(
    *,
    source_id: str = "sim-temperature-test",
    measurement: EnvironmentalMeasurement = EnvironmentalMeasurement.TEMPERATURE,
    mode: SimulationMode = SimulationMode.STATIC,
    seed: int = 1234,
    initial_value: float = 20.0,
    minimum_value: float = 10.0,
    maximum_value: float = 30.0,
    maximum_step: float = 1.0,
) -> EnvironmentalSensorConfig:
    return EnvironmentalSensorConfig(
        source_id=source_id,
        measurement=measurement,
        mode=mode,
        cadence_seconds=2.5,
        initial_value=initial_value,
        minimum_value=minimum_value,
        maximum_value=maximum_value,
        maximum_step=maximum_step,
        seed=seed,
        scope_kind=ScopeKind.SITE,
        scope_id="test-site",
    )


class FixedClock:
    """Return one deterministic instant and expose unexpected waits."""

    def __init__(self, value: datetime = FIXED_TIME) -> None:
        self.value = value
        self.waits: list[float] = []

    def now(self) -> datetime:
        return self.value

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        del stop_requested
        self.waits.append(seconds)


class AdvancingClock:
    """Advance without sleeping and stop after a controlled number of waits."""

    def __init__(self, *, stop_after_waits: int) -> None:
        self.current = FIXED_TIME
        self.stop_after_waits = stop_after_waits
        self.waits: list[float] = []

    def now(self) -> datetime:
        return self.current

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        self.waits.append(seconds)
        self.current += timedelta(seconds=seconds)
        if len(self.waits) >= self.stop_after_waits:
            stop_requested.set()
        await asyncio.sleep(0)


class BlockingClock:
    """Hold a periodic source in its cadence until stop interrupts it."""

    def __init__(self) -> None:
        self.waiting = asyncio.Event()

    def now(self) -> datetime:
        return FIXED_TIME

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        del seconds
        self.waiting.set()
        await stop_requested.wait()


class RecordingPublisher:
    """Record immutable publication calls and lifecycle state."""

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.calls: list[tuple[TopicRoute, ObservationEnvelopeV1]] = []

    async def start(self) -> None:
        self.started = True

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        self.calls.append((route, envelope))

    async def close(self) -> None:
        self.closed = True


class BlockingPublisher(RecordingPublisher):
    """Expose an in-flight publication so graceful stop can be observed."""

    def __init__(self) -> None:
        super().__init__()
        self.publishing = asyncio.Event()
        self.release = asyncio.Event()

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        self.calls.append((route, envelope))
        self.publishing.set()
        await self.release.wait()


class FailingPublisher(RecordingPublisher):
    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        del route, envelope
        raise BrokerUnavailable("test publisher exhausted")


class ConcurrentPublisher(RecordingPublisher):
    """Hold static calls until every configured source is inside publish."""

    def __init__(self, expected: int) -> None:
        super().__init__()
        self.expected = expected
        self.active = 0
        self.maximum_active = 0
        self.all_entered = asyncio.Event()

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.calls.append((route, envelope))
        if self.active == self.expected:
            self.all_entered.set()
        await self.all_entered.wait()
        self.active -= 1


class FakeMessageInfo:
    def __init__(self, published: bool) -> None:
        self.rc = mqtt.MQTT_ERR_SUCCESS
        self._published = published

    def wait_for_publish(self, timeout: float | None = None) -> None:
        del timeout

    def is_published(self) -> bool:
        return self._published


class RetryPahoClient:
    """Paho-shaped client that requires two PUBACK attempts."""

    def __init__(self) -> None:
        self.on_connect: Any = None
        self.on_connect_fail: Any = None
        self.on_disconnect: Any = None
        self.payloads: list[bytes] = []

    def reconnect_delay_set(self, min_delay: int, max_delay: int) -> None:
        assert (min_delay, max_delay) == (1, 30)

    def connect_async(
        self,
        host: str,
        port: int,
        keepalive: int,
        *,
        clean_start: bool,
    ) -> None:
        del host, port, keepalive, clean_start
        self.on_connect(self, None, None, 0, None)

    def loop_start(self) -> MQTTErrorCode:
        return mqtt.MQTT_ERR_SUCCESS

    def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> FakeMessageInfo:
        del topic
        assert qos == 1
        assert retain is False
        self.payloads.append(payload)
        return FakeMessageInfo(published=len(self.payloads) == 2)

    def disconnect(self) -> MQTTErrorCode:
        return mqtt.MQTT_ERR_SUCCESS

    def loop_stop(self) -> MQTTErrorCode:
        return mqtt.MQTT_ERR_SUCCESS


def accepts_source_lifecycle(source: SourceLifecycle) -> SourceLifecycle:
    """Static typing assertion for the accepted M0 lifecycle contract."""

    return source


def test_development_configuration_is_versioned_and_has_three_sources() -> None:
    configuration = SimulatorConfiguration.from_json_file(
        REPOSITORY_ROOT / "configs" / "simulator.development.json"
    )

    assert configuration.schema_version == "1.0"
    assert [sensor.measurement for sensor in configuration.sensors] == [
        EnvironmentalMeasurement.TEMPERATURE,
        EnvironmentalMeasurement.RELATIVE_HUMIDITY,
        EnvironmentalMeasurement.NH3,
    ]
    assert len({sensor.source_id for sensor in configuration.sensors}) == 3


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"cadence_seconds": 0.0}, "greater than 0"),
        ({"initial_value": math.nan}, "finite number"),
        ({"minimum_value": 31.0}, "minimum_value must not exceed"),
        ({"initial_value": 31.0}, "initial_value must be within"),
        ({"source_id": "Invalid Source"}, "String should match pattern"),
        ({"scope_id": "Invalid Scope"}, "String should match pattern"),
    ],
)
def test_invalid_sensor_configuration_fails_explicitly(
    changes: dict[str, object],
    message: str,
) -> None:
    values = sensor_config().model_dump()
    values.update(changes)

    with pytest.raises(ValidationError, match=message):
        EnvironmentalSensorConfig.model_validate(values)


@pytest.mark.parametrize(
    "changes",
    [
        {
            "measurement": EnvironmentalMeasurement.RELATIVE_HUMIDITY,
            "initial_value": 50.0,
            "minimum_value": -1.0,
            "maximum_value": 90.0,
        },
        {
            "measurement": EnvironmentalMeasurement.NH3,
            "initial_value": 1.0,
            "minimum_value": -1.0,
            "maximum_value": 10.0,
        },
    ],
)
def test_measurement_specific_invalid_bounds_are_rejected_before_runtime(
    changes: dict[str, object],
) -> None:
    values = sensor_config().model_dump()
    values.update(changes)

    with pytest.raises(ValidationError, match="bounds must be"):
        EnvironmentalSensorConfig.model_validate(values)


def test_duplicate_source_ids_are_rejected() -> None:
    config = sensor_config()
    with pytest.raises(ValidationError, match="source_id values must be unique"):
        SimulatorConfiguration(schema_version="1.0", sensors=(config, config))


@pytest.mark.asyncio
async def test_fixed_seed_source_and_clock_reproduce_complete_sequence() -> None:
    first = EnvironmentalSensorSimulator(sensor_config(), clock=FixedClock())
    second = EnvironmentalSensorSimulator(sensor_config(), clock=FixedClock())
    await first.open()
    await second.open()

    first_sequence = [first.next_observation() for _ in range(8)]
    second_sequence = [second.next_observation() for _ in range(8)]

    assert first_sequence == second_sequence
    assert [serialize_observation(item) for item in first_sequence] == [
        serialize_observation(item) for item in second_sequence
    ]
    assert len({item.event_id for item in first_sequence}) == len(first_sequence)
    assert all(item.event_id.version == 7 for item in first_sequence)


@pytest.mark.asyncio
async def test_different_seeds_change_values_and_event_identity() -> None:
    first = EnvironmentalSensorSimulator(sensor_config(seed=1), clock=FixedClock())
    second = EnvironmentalSensorSimulator(sensor_config(seed=2), clock=FixedClock())
    await first.open()
    await second.open()

    first_sequence = [first.next_observation() for _ in range(3)]
    second_sequence = [second.next_observation() for _ in range(3)]

    assert first_sequence[0].event_id != second_sequence[0].event_id
    assert [item.payload.value for item in first_sequence[1:]] != [
        item.payload.value for item in second_sequence[1:]
    ]


@pytest.mark.asyncio
async def test_random_walk_is_bounded_and_finite() -> None:
    source = EnvironmentalSensorSimulator(
        sensor_config(
            initial_value=0.5,
            minimum_value=0.0,
            maximum_value=1.0,
            maximum_step=100.0,
        ),
        clock=FixedClock(),
    )
    await source.open()

    values = [source.next_observation().payload.value for _ in range(1_000)]

    assert all(0.0 <= value <= 1.0 for value in values)
    assert all(math.isfinite(value) for value in values)


@pytest.mark.parametrize(
    ("measurement", "initial", "minimum", "maximum", "payload_class", "unit"),
    [
        (
            EnvironmentalMeasurement.TEMPERATURE,
            20.0,
            -20.0,
            50.0,
            TemperaturePayload,
            "Cel",
        ),
        (
            EnvironmentalMeasurement.RELATIVE_HUMIDITY,
            50.0,
            0.0,
            100.0,
            RelativeHumidityPayload,
            "%",
        ),
        (
            EnvironmentalMeasurement.NH3,
            5.0,
            0.0,
            100.0,
            AmmoniaConcentrationPayload,
            "[ppm]",
        ),
    ],
)
@pytest.mark.asyncio
async def test_generated_envelope_uses_exact_m1_payload_unit_and_provenance(
    measurement: EnvironmentalMeasurement,
    initial: float,
    minimum: float,
    maximum: float,
    payload_class: type[object],
    unit: str,
) -> None:
    source = EnvironmentalSensorSimulator(
        sensor_config(
            measurement=measurement,
            initial_value=initial,
            minimum_value=minimum,
            maximum_value=maximum,
        ),
        clock=FixedClock(datetime(2026, 9, 4, 7, tzinfo=timezone(timedelta(hours=-5)))),
    )
    await source.open()

    envelope = source.next_observation()

    assert isinstance(envelope.payload, payload_class)
    assert envelope.payload_type is measurement.payload_type
    assert envelope.payload.unit == unit
    assert envelope.source.origin is SourceOrigin.SYNTHETIC
    assert envelope.source.delivery is SourceDelivery.LIVE
    assert envelope.event_time == FIXED_TIME
    assert envelope.event_time.tzinfo is UTC
    assert envelope.replay_time is None
    assert envelope.ingest_time is None
    assert accepts_source_lifecycle(source) is source


@pytest.mark.asyncio
async def test_naive_clock_fails_without_advancing_value_state() -> None:
    source = EnvironmentalSensorSimulator(
        sensor_config(),
        clock=FixedClock(datetime(2026, 9, 4, 12)),
    )
    await source.open()

    with pytest.raises(ValueError, match="timezone-aware"):
        source.next_observation()


@pytest.mark.asyncio
async def test_static_mode_publishes_once_without_waiting() -> None:
    clock = FixedClock()
    source = EnvironmentalSensorSimulator(sensor_config(), clock=clock)
    publisher = RecordingPublisher()
    runner = MultiSourceSimulatorRunner((source,), publisher)

    await runner.run()

    assert publisher.started
    assert publisher.closed
    assert len(publisher.calls) == 1
    assert clock.waits == []
    assert source.state is SimulatorState.STOPPED
    assert source.task is not None and source.task.done()


@pytest.mark.asyncio
async def test_periodic_mode_uses_fixed_delay_and_stops_without_sleep() -> None:
    clock = AdvancingClock(stop_after_waits=3)
    source = EnvironmentalSensorSimulator(
        sensor_config(mode=SimulationMode.PERIODIC),
        clock=clock,
    )
    publisher = RecordingPublisher()

    await MultiSourceSimulatorRunner((source,), publisher).run()

    assert len(publisher.calls) == 3
    assert clock.waits == [2.5, 2.5, 2.5]
    assert [call[1].event_time for call in publisher.calls] == [
        FIXED_TIME,
        FIXED_TIME + timedelta(seconds=2.5),
        FIXED_TIME + timedelta(seconds=5),
    ]
    assert source.state is SimulatorState.STOPPED


@pytest.mark.asyncio
async def test_double_start_is_rejected() -> None:
    source = EnvironmentalSensorSimulator(sensor_config(), clock=FixedClock())
    publisher = RecordingPublisher()
    await source.open()
    await source.start(publisher)

    with pytest.raises(RuntimeError, match="cannot start"):
        await source.start(publisher)

    await source.wait()
    await source.close()


@pytest.mark.asyncio
async def test_stop_interrupts_periodic_wait_and_leaves_no_task() -> None:
    clock = BlockingClock()
    source = EnvironmentalSensorSimulator(
        sensor_config(mode=SimulationMode.PERIODIC),
        clock=clock,
    )
    publisher = RecordingPublisher()
    await source.open()
    await source.start(publisher)
    await asyncio.wait_for(clock.waiting.wait(), timeout=1)

    await asyncio.wait_for(source.stop(), timeout=1)

    assert len(publisher.calls) == 1
    assert source.state is SimulatorState.STOPPED
    assert source.task is not None and source.task.done()


@pytest.mark.asyncio
async def test_stop_during_publication_waits_for_bounded_publisher_operation() -> None:
    source = EnvironmentalSensorSimulator(
        sensor_config(mode=SimulationMode.PERIODIC),
        clock=FixedClock(),
    )
    publisher = BlockingPublisher()
    await source.open()
    await source.start(publisher)
    await publisher.publishing.wait()

    stop_task = asyncio.create_task(source.stop())
    await asyncio.sleep(0)
    assert not stop_task.done()
    publisher.release.set()
    await asyncio.wait_for(stop_task, timeout=1)

    assert len(publisher.calls) == 1
    assert source.state is SimulatorState.STOPPED
    assert source.task is not None and source.task.done()


@pytest.mark.asyncio
async def test_publication_failure_is_retained_and_propagated() -> None:
    source = EnvironmentalSensorSimulator(sensor_config(), clock=FixedClock())
    await source.open()
    await source.start(FailingPublisher())

    with pytest.raises(BrokerUnavailable, match="exhausted"):
        await source.wait()

    assert isinstance(source.failure, BrokerUnavailable)
    assert source.state is SimulatorState.FAILED
    await source.close()
    await source.close()


@pytest.mark.asyncio
async def test_three_static_sources_publish_concurrently_and_cleanup() -> None:
    configurations = (
        sensor_config(
            source_id="sim-temperature",
            measurement=EnvironmentalMeasurement.TEMPERATURE,
        ),
        sensor_config(
            source_id="sim-humidity",
            measurement=EnvironmentalMeasurement.RELATIVE_HUMIDITY,
            initial_value=50.0,
            minimum_value=0.0,
            maximum_value=100.0,
        ),
        sensor_config(
            source_id="sim-nh3",
            measurement=EnvironmentalMeasurement.NH3,
            initial_value=5.0,
            minimum_value=0.0,
            maximum_value=100.0,
        ),
    )
    sources = tuple(
        EnvironmentalSensorSimulator(config, clock=FixedClock()) for config in configurations
    )
    publisher = ConcurrentPublisher(expected=3)

    await asyncio.wait_for(MultiSourceSimulatorRunner(sources, publisher).run(), timeout=1)

    assert publisher.maximum_active == 3
    assert {call[1].source.source_id for call in publisher.calls} == {
        "sim-temperature",
        "sim-humidity",
        "sim-nh3",
    }
    assert all(source.task is not None and source.task.done() for source in sources)


@pytest.mark.asyncio
async def test_generated_event_keeps_exact_identity_and_bytes_across_m1_retry() -> None:
    source = EnvironmentalSensorSimulator(sensor_config(), clock=FixedClock())
    await source.open()
    envelope = source.next_observation()
    fake = RetryPahoClient()
    publisher = MqttTelemetryPublisher(
        MqttConnectionSettings(
            connect_timeout_seconds=0.01,
            publish_timeout_seconds=0.01,
            publish_attempts=2,
        ),
        client_id="m2-retry-test",
        client=cast(mqtt.Client, fake),
    )

    await publisher.publish(source.route, envelope)
    await publisher.close()

    assert fake.payloads == [serialize_observation(envelope), serialize_observation(envelope)]
    assert [
        ObservationEnvelopeV1.model_validate_json(payload).event_id for payload in fake.payloads
    ] == [envelope.event_id, envelope.event_id]
