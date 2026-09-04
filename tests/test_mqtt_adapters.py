"""Publisher retry, connection-state and explicit broker-failure tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, cast

import paho.mqtt.client as mqtt
import pytest
from paho.mqtt.enums import MQTTErrorCode
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from pigwatch_schemas import serialize_observation
from pigwatch_telemetry import (
    BrokerUnavailable,
    ConnectionState,
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
    ObservationCategory,
    PersistenceUnavailable,
    ProcessingResult,
    ProcessingStatus,
    ScopeKind,
    TopicRoute,
)
from pigwatch_telemetry.mqtt import InboundMessage
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

    def disconnect(
        self,
        reasoncode: ReasonCode | None = None,
        properties: Properties | None = None,
    ) -> MQTTErrorCode:
        del reasoncode, properties
        return mqtt.MQTT_ERR_SUCCESS

    def loop_stop(self) -> None:
        self.started = False


class FakeConsumerPahoClient(FakePahoClient):
    """Paho-shaped consumer that records manual acknowledgements."""

    def __init__(self) -> None:
        super().__init__()
        self.on_subscribe: Any = None
        self.on_message: Any = None
        self.acknowledgements: list[tuple[int, int]] = []
        self.connect_properties: Properties | None = None
        self.subscription: tuple[str, int] | None = None
        self.subscription_mid = 7
        self.ack_hook: Callable[[], None] | None = None
        self.reconnect_hook: Callable[[], None] | None = None
        self.disconnect_calls = 0
        self.reconnect_calls = 0

    def connect_async(
        self,
        host: str,
        port: int,
        keepalive: int,
        *,
        clean_start: bool,
        properties: Properties | None = None,
    ) -> None:
        del host, port, keepalive
        assert clean_start is False
        self.connect_properties = properties

    def subscribe(self, topic: str, qos: int = 0) -> tuple[MQTTErrorCode, int]:
        self.subscription = (topic, qos)
        return mqtt.MQTT_ERR_SUCCESS, self.subscription_mid

    def emit_connect(self) -> None:
        self.on_connect(
            self,
            None,
            None,
            ReasonCode(PacketTypes.CONNACK, identifier=0),
            None,
        )

    def emit_suback(self, *, qos: int = 1) -> None:
        self.on_subscribe(
            self,
            None,
            self.subscription_mid,
            [ReasonCode(PacketTypes.SUBACK, identifier=qos)],
            None,
        )

    def ack(self, message_id: int, qos: int) -> int:
        self.acknowledgements.append((message_id, qos))
        hook, self.ack_hook = self.ack_hook, None
        if hook is not None:
            hook()
        return mqtt.MQTT_ERR_SUCCESS

    def disconnect(
        self,
        reasoncode: ReasonCode | None = None,
        properties: Properties | None = None,
    ) -> MQTTErrorCode:
        del reasoncode, properties
        self.disconnect_calls += 1
        self.on_disconnect(
            self,
            None,
            None,
            ReasonCode(PacketTypes.DISCONNECT, identifier=0),
            None,
        )
        return mqtt.MQTT_ERR_SUCCESS

    def reconnect(self) -> MQTTErrorCode:
        self.reconnect_calls += 1
        self.emit_connect()
        self.emit_suback()
        if self.reconnect_hook is not None:
            self.reconnect_hook()
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


class BlockingProcessor:
    """Track active work while holding processing until the test releases it."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.active = 0
        self.max_active = 0
        self.calls = 0

    async def process(self, topic: str, payload: bytes) -> ProcessingResult:
        del topic, payload
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        try:
            await self.release.wait()
            return ProcessingResult(ProcessingStatus.ACCEPTED, None)
        finally:
            self.active -= 1


class SlowCancellationProcessor:
    """Expose cancellation cleanup so close can prove it waits for settlement."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cleaned = asyncio.Event()

    async def process(self, topic: str, payload: bytes) -> ProcessingResult:
        del topic, payload
        self.started.set()
        try:
            await asyncio.Event().wait()
            raise AssertionError("test cancellation gate was unexpectedly released")
        except asyncio.CancelledError:
            await asyncio.sleep(0.05)
            self.cleaned.set()
            raise


class RetryProcessor:
    """Remain in persistence retry until shutdown wakes or cancels the task."""

    def __init__(self) -> None:
        self.called = asyncio.Event()

    async def process(self, topic: str, payload: bytes) -> ProcessingResult:
        del topic, payload
        self.called.set()
        raise PersistenceUnavailable("test outage")


class RecordingProcessor:
    """Record exact delivery ownership while tracking the concurrency boundary."""

    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.active = 0
        self.max_active = 0

    async def process(self, topic: str, payload: bytes) -> ProcessingResult:
        del topic
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self.payloads.append(payload)
            await asyncio.sleep(0)
            return ProcessingResult(ProcessingStatus.ACCEPTED, None)
        finally:
            self.active -= 1


async def wait_for(predicate: Callable[[], bool], *, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition did not become true before timeout")


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
        fake_processor,
        client=cast(mqtt.Client, fake_client),
    )
    message = InboundMessage(
        topic=route().topic(),
        payload=b"{}",
        message_id=42,
        qos=1,
    )

    result = await worker._process_until_durable(message)

    assert result == ProcessingResult(ProcessingStatus.ACCEPTED, None)
    assert fake_processor.calls == 2
    assert fake_client.acknowledgements == [(42, 1)]


@pytest.mark.asyncio
async def test_consumer_readiness_requires_successful_suback() -> None:
    fake_client = FakeConsumerPahoClient()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(receive_maximum=8, processing_concurrency=2),
        TimeoutThenSucceedProcessor(),
        client=cast(mqtt.Client, fake_client),
    )

    await worker.start()
    assert not bool(worker.is_connected)
    assert not bool(worker.is_ready)

    fake_client.emit_connect()
    assert bool(worker.is_connected)
    assert not bool(worker.is_subscribed)
    assert not bool(worker.is_ready)
    assert worker.state.value == ConnectionState.SUBSCRIBING.value
    assert fake_client.subscription == ("pigwatch/v1/observations/+/+/+/+", 1)
    assert fake_client.connect_properties is not None
    assert cast(Any, fake_client.connect_properties).ReceiveMaximum == 8

    fake_client.emit_suback()
    assert bool(worker.is_subscribed)
    assert bool(worker.is_ready)
    assert worker.state.value == ConnectionState.CONNECTED.value
    assert worker.subscription_count == 1

    await worker.close()


@pytest.mark.asyncio
async def test_consumer_rejects_non_qos_one_suback_for_readiness() -> None:
    fake_client = FakeConsumerPahoClient()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(),
        TimeoutThenSucceedProcessor(),
        client=cast(mqtt.Client, fake_client),
    )

    await worker.start()
    fake_client.emit_connect()
    fake_client.emit_suback(qos=0)

    assert bool(worker.is_connected)
    assert not bool(worker.is_subscribed)
    assert not bool(worker.is_ready)
    await worker.close()


@pytest.mark.asyncio
async def test_receive_limit_and_semaphore_bound_pending_and_active_processing() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = BlockingProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(receive_maximum=6, processing_concurrency=2),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    fake_client.emit_connect()
    fake_client.emit_suback()
    assert worker.is_ready

    for message_id in range(1, 7):
        worker._schedule_message(InboundMessage(route().topic(), b"{}", message_id, 1))
    await processor.started.wait()
    await wait_for(lambda: worker.active_count == 2)

    assert worker.pending_count == 6
    assert worker.active_count == 2
    assert processor.max_active == 2
    assert bool(worker.is_saturated)
    assert not bool(worker.is_ready)

    processor.release.set()
    await wait_for(lambda: worker.pending_count == 0)
    assert len(fake_client.acknowledgements) == 6
    assert not bool(worker.is_saturated)
    assert bool(worker.is_ready)
    await worker.close()


@pytest.mark.asyncio
async def test_ack_handoff_releases_capacity_before_done_callback() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = RecordingProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(receive_maximum=1, processing_concurrency=1),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    fake_client.emit_connect()
    fake_client.emit_suback()
    handoff_state: list[tuple[int, bool, bool]] = []

    def deliver_replacement_during_ack() -> None:
        # ack() is still on the first task's stack, so its done callback cannot have run.
        handoff_state.append((worker.pending_count, worker.is_saturated, worker.is_ready))
        worker._schedule_message(InboundMessage(route().topic(), b"second", 2, 1))
        handoff_state.append((worker.pending_count, worker.is_saturated, worker.is_ready))

    fake_client.ack_hook = deliver_replacement_during_ack
    worker._schedule_message(InboundMessage(route().topic(), b"first", 1, 1))

    await wait_for(lambda: fake_client.acknowledgements == [(1, 1), (2, 1)])
    await wait_for(lambda: worker.pending_count == 0 and worker.is_ready)

    assert handoff_state == [(0, False, True), (1, True, False)]
    assert processor.payloads == [b"first", b"second"]
    assert processor.max_active == 1
    assert worker.active_count == 0
    assert not worker.is_saturated
    await worker.close()


@pytest.mark.asyncio
async def test_unexpected_receive_overflow_forces_persistent_session_redelivery() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = BlockingProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(receive_maximum=1, processing_concurrency=1),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    fake_client.emit_connect()
    fake_client.emit_suback()
    first = InboundMessage(route().topic(), b"first", 1, 1)
    overflow = InboundMessage(route().topic(), b"overflow", 2, 1)

    worker._schedule_message(first)
    await processor.started.wait()
    assert worker.pending_count == 1
    assert bool(worker.is_saturated)
    assert not worker.is_ready

    event_loop = asyncio.get_running_loop()

    def redeliver_after_reconnect() -> None:
        event_loop.call_soon_threadsafe(worker._schedule_message, overflow)

    fake_client.reconnect_hook = redeliver_after_reconnect
    worker._schedule_message(overflow)
    await wait_for(lambda: fake_client.disconnect_calls == 1)
    assert not worker.is_ready

    processor.release.set()
    await wait_for(lambda: fake_client.reconnect_calls == 1)
    await wait_for(lambda: fake_client.acknowledgements == [(1, 1), (2, 1)])
    await wait_for(lambda: worker.pending_count == 0 and worker.is_ready)

    assert processor.calls == 2
    assert processor.max_active == 1
    assert worker.active_count == 0
    assert not bool(worker.is_saturated)
    await worker.close()


@pytest.mark.asyncio
async def test_close_waits_for_slow_cancellation_cleanup() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = SlowCancellationProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(
            shutdown_grace_seconds=0.01,
            shutdown_timeout_seconds=0.5,
        ),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    worker._schedule_message(InboundMessage(route().topic(), b"{}", 11, 1))
    await processor.started.wait()

    await worker.close()

    assert processor.cleaned.is_set()
    assert worker.pending_count == 0
    assert fake_client.acknowledgements == []


@pytest.mark.asyncio
async def test_close_wakes_processing_that_is_waiting_to_retry() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = RetryProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(
            persistence_retry_initial_seconds=5,
            persistence_retry_max_seconds=5,
            shutdown_grace_seconds=0.1,
            shutdown_timeout_seconds=0.5,
        ),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    worker._schedule_message(InboundMessage(route().topic(), b"{}", 12, 1))
    await processor.called.wait()

    await worker.close()

    assert worker.pending_count == 0
    assert fake_client.acknowledgements == []


@pytest.mark.asyncio
async def test_close_allows_near_commit_work_to_ack_during_grace_period() -> None:
    fake_client = FakeConsumerPahoClient()
    processor = BlockingProcessor()
    worker = MqttIngestionWorker(
        MqttConnectionSettings(
            shutdown_grace_seconds=0.2,
            shutdown_timeout_seconds=0.5,
        ),
        processor,
        client=cast(mqtt.Client, fake_client),
    )
    await worker.start()
    worker._schedule_message(InboundMessage(route().topic(), b"{}", 13, 1))
    await processor.started.wait()

    closing = asyncio.create_task(worker.close())
    await asyncio.sleep(0.02)
    processor.release.set()
    await closing

    assert fake_client.acknowledgements == [(13, 1)]
    assert worker.pending_count == 0
