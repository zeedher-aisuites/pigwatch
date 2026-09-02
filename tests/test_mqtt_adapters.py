"""Publisher retry, connection-state and explicit broker-failure tests."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import paho.mqtt.client as mqtt
import pytest

from pigwatch_schemas import serialize_observation
from pigwatch_telemetry import (
    BrokerUnavailable,
    ConnectionState,
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
    ObservationCategory,
    ProcessingResult,
    ProcessingStatus,
    ScopeKind,
    TelemetryProcessor,
    TopicRoute,
)
from tests.support import load_observation_fixture


class FakeMessageInfo:
    """Controllable PUBACK result returned by the fake Paho client."""

    def __init__(self, published: bool) -> None:
        self.rc = mqtt.MQTT_ERR_SUCCESS
        self._published = published

    def wait_for_publish(self, timeout: float | None = None) -> None:
        del timeout

    def is_published(self) -> bool:
        return self._published


class FakePahoClient:
    """Minimal Paho-shaped publisher client that fails its first PUBACK."""

    def __init__(self) -> None:
        self.on_connect: Any = None
        self.on_connect_fail: Any = None
        self.on_disconnect: Any = None
        self.payloads: list[bytes] = []
        self.topics: list[str] = []
        self.started = False

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

    def loop_start(self) -> None:
        self.started = True

    def publish(self, topic: str, payload: bytes, qos: int, retain: bool) -> FakeMessageInfo:
        assert qos == 1
        assert retain is False
        self.topics.append(topic)
        self.payloads.append(payload)
        return FakeMessageInfo(published=len(self.payloads) > 1)

    def disconnect(self) -> None:
        return None

    def loop_stop(self) -> None:
        self.started = False


class FakeConsumerPahoClient(FakePahoClient):
    """Paho-shaped consumer that records manual acknowledgements."""

    def __init__(self) -> None:
        super().__init__()
        self.acknowledgements: list[tuple[int, int]] = []

    def ack(self, message_id: int, qos: int) -> int:
        self.acknowledgements.append((message_id, qos))
        return mqtt.MQTT_ERR_SUCCESS


class TimeoutThenSucceedProcessor:
    """Simulate a database operation stranded across an outage."""

    def __init__(self) -> None:
        self.calls = 0

    async def process(self, topic: str, payload: bytes) -> ProcessingResult:
        del topic, payload
        self.calls += 1
        if self.calls == 1:
            await asyncio.Event().wait()
        return ProcessingResult(ProcessingStatus.ACCEPTED, None)


def route() -> TopicRoute:
    return TopicRoute(
        scope_kind=ScopeKind.SITE,
        scope_id="test-site",
        source_id="fixture-synthetic-live",
        category=ObservationCategory.TEMPERATURE,
    )


@pytest.mark.asyncio
async def test_publish_retry_preserves_exact_event_bytes_until_puback() -> None:
    fake = FakePahoClient()
    publisher = MqttTelemetryPublisher(
        MqttConnectionSettings(
            connect_timeout_seconds=0.01,
            publish_timeout_seconds=0.01,
            publish_attempts=2,
        ),
        client_id="test-publisher",
        client=cast(mqtt.Client, fake),
    )
    envelope = load_observation_fixture("synthetic-live")

    await publisher.publish(route(), envelope)
    await publisher.close()

    assert fake.payloads == [serialize_observation(envelope), serialize_observation(envelope)]
    assert fake.topics == [route().topic(), route().topic()]
    assert publisher.state is ConnectionState.STOPPED


@pytest.mark.asyncio
async def test_publish_fails_explicitly_when_broker_is_unavailable() -> None:
    publisher = MqttTelemetryPublisher(
        MqttConnectionSettings(
            host="127.0.0.1",
            port=65_534,
            connect_timeout_seconds=0.05,
            publish_timeout_seconds=0.05,
            publish_attempts=1,
        ),
        client_id="test-unavailable-publisher",
    )

    with pytest.raises(BrokerUnavailable):
        await publisher.publish(route(), load_observation_fixture("synthetic-live"))

    assert publisher.is_connected is False
    await publisher.close()


@pytest.mark.asyncio
async def test_publisher_rejects_pigwatch_assigned_ingest_time() -> None:
    envelope = load_observation_fixture("synthetic-live").accepted_at(
        load_observation_fixture("synthetic-live").event_time
    )
    publisher = MqttTelemetryPublisher(
        MqttConnectionSettings(connect_timeout_seconds=0.01, publish_attempts=1),
        client_id="test-invalid-envelope",
        client=cast(mqtt.Client, FakePahoClient()),
    )

    with pytest.raises(ValueError, match="ingest_time null"):
        await publisher.publish(route(), envelope)


@pytest.mark.asyncio
async def test_consumer_times_out_stranded_database_attempt_before_retry_and_ack() -> None:
    fake_client = FakeConsumerPahoClient()
    fake_processor = TimeoutThenSucceedProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(
            persistence_attempt_timeout_seconds=0.01,
            persistence_retry_initial_seconds=0.01,
            persistence_retry_max_seconds=0.01,
        ),
        cast(TelemetryProcessor, fake_processor),
        client=cast(mqtt.Client, fake_client),
    )
    message = cast(
        mqtt.MQTTMessage,
        SimpleNamespace(topic=route().topic(), payload=b"{}", mid=42, qos=1),
    )

    result = await worker._process_until_durable(
        cast(mqtt.Client, fake_client),
        message,
    )

    assert result == ProcessingResult(ProcessingStatus.ACCEPTED, None)
    assert fake_processor.calls == 2
    assert fake_client.acknowledgements == [(42, 1)]
