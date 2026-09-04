"""Reusable MQTT v5 publisher and manually acknowledged ingestion worker."""

from __future__ import annotations

import asyncio
import logging
import math
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from pigwatch_schemas import ObservationEnvelopeV1, serialize_observation
from pigwatch_telemetry.models import (
    BrokerUnavailable,
    PersistenceUnavailable,
    ProcessingResult,
    ShutdownTimeout,
)
from pigwatch_telemetry.topics import (
    OBSERVATION_TOPIC_FILTER,
    PAYLOAD_CATEGORY,
    TopicRoute,
    validate_route_matches_envelope,
)

LOGGER = logging.getLogger(__name__)


class ConnectionState(StrEnum):
    """Observable lifecycle state shared by MQTT adapters."""

    STOPPED = "STOPPED"
    CONNECTING = "CONNECTING"
    SUBSCRIBING = "SUBSCRIBING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"


@dataclass(frozen=True, slots=True)
class MqttConnectionSettings:
    """Non-secret MQTT connection and retry settings."""

    host: str = "127.0.0.1"
    port: int = 1883
    keepalive_seconds: int = 30
    connect_timeout_seconds: float = 5.0
    publish_timeout_seconds: float = 5.0
    publish_attempts: int = 3
    session_expiry_seconds: int = 86_400
    persistence_attempt_timeout_seconds: float = 10.0
    persistence_retry_initial_seconds: float = 1.0
    persistence_retry_max_seconds: float = 30.0
    receive_maximum: int = 16
    processing_concurrency: int = 4
    shutdown_grace_seconds: float = 0.25
    shutdown_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.publish_attempts < 1:
            raise ValueError("publish_attempts must be at least one")
        if not 1 <= self.receive_maximum <= 65_535:
            raise ValueError("receive_maximum must be between 1 and 65535")
        if not 1 <= self.processing_concurrency <= self.receive_maximum:
            raise ValueError("processing_concurrency must be between 1 and receive_maximum")
        durations = {
            "keepalive_seconds": self.keepalive_seconds,
            "connect_timeout_seconds": self.connect_timeout_seconds,
            "publish_timeout_seconds": self.publish_timeout_seconds,
            "session_expiry_seconds": self.session_expiry_seconds,
            "persistence_attempt_timeout_seconds": self.persistence_attempt_timeout_seconds,
            "persistence_retry_initial_seconds": self.persistence_retry_initial_seconds,
            "persistence_retry_max_seconds": self.persistence_retry_max_seconds,
            "shutdown_grace_seconds": self.shutdown_grace_seconds,
            "shutdown_timeout_seconds": self.shutdown_timeout_seconds,
        }
        invalid_durations = [
            name
            for name, duration in durations.items()
            if not math.isfinite(duration) or duration <= 0
        ]
        if invalid_durations:
            raise ValueError(
                "MQTT durations must be finite and greater than zero: "
                + ", ".join(invalid_durations)
            )
        if self.shutdown_grace_seconds > self.shutdown_timeout_seconds:
            raise ValueError("shutdown grace must fit within the shutdown timeout")


def _connection_failed(reason_code: Any) -> bool:
    return bool(getattr(reason_code, "is_failure", reason_code != 0))


class TelemetryMessageProcessor(Protocol):
    """Processing boundary consumed by the MQTT worker and deterministic tests."""

    async def process(self, topic: str, raw_message: bytes) -> ProcessingResult: ...


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """Immutable copy of Paho callback data needed after the callback returns."""

    topic: str
    payload: bytes
    message_id: int
    qos: int


class MqttTelemetryPublisher:
    """QoS 1 publisher that preserves exact event identity and bytes across retries."""

    def __init__(
        self,
        settings: MqttConnectionSettings,
        *,
        client_id: str,
        client: mqtt.Client | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
        )
        self._client.on_connect = self._on_connect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._connected = threading.Event()
        self._state = ConnectionState.STOPPED
        self._started = False
        self._stopping = False
        self._connection_count = 0

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state is ConnectionState.CONNECTED and self._connected.is_set()

    @property
    def connection_count(self) -> int:
        """Return successful connections, including reconnects, for observability."""

        return self._connection_count

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        del client, userdata, flags, properties
        if _connection_failed(reason_code):
            self._state = ConnectionState.DISCONNECTED
            self._connected.clear()
            return
        self._state = ConnectionState.CONNECTED
        self._connection_count += 1
        self._connected.set()
        LOGGER.info("mqtt_publisher_connected", extra={"broker_state": self._state.value})

    def _on_connect_fail(self, client: mqtt.Client, userdata: Any) -> None:
        del client, userdata
        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
        LOGGER.warning("mqtt_publisher_connect_failed", extra={"broker_state": self._state.value})

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        del client, userdata, disconnect_flags, reason_code, properties
        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
        if not self._stopping:
            LOGGER.warning(
                "mqtt_publisher_disconnected",
                extra={"broker_state": self._state.value},
            )

    async def start(self) -> None:
        if self._started:
            return
        self._stopping = False
        self._state = ConnectionState.CONNECTING
        self._client.connect_async(
            self._settings.host,
            self._settings.port,
            self._settings.keepalive_seconds,
            clean_start=True,
        )
        self._client.loop_start()
        self._started = True

    async def wait_until_connected(self, timeout: float | None = None) -> bool:
        wait_for = timeout or self._settings.connect_timeout_seconds
        return await asyncio.to_thread(self._connected.wait, wait_for)

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        if envelope.ingest_time is not None:
            raise ValueError("publisher accepts wire envelopes with ingest_time null only")
        validate_route_matches_envelope(
            route,
            source_id=envelope.source.source_id,
            payload_type=envelope.payload_type,
        )
        if route.category is not PAYLOAD_CATEGORY[envelope.payload_type]:
            raise ValueError("topic category does not match payload")
        if not self._started:
            await self.start()

        payload = serialize_observation(envelope)
        delay = 0.25
        for attempt in range(1, self._settings.publish_attempts + 1):
            if not await self.wait_until_connected():
                if attempt < self._settings.publish_attempts:
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                break
            info = self._client.publish(route.topic(), payload, qos=1, retain=False)
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                try:
                    await asyncio.to_thread(
                        info.wait_for_publish,
                        self._settings.publish_timeout_seconds,
                    )
                except (RuntimeError, ValueError):
                    pass
                if info.is_published():
                    LOGGER.info(
                        "telemetry_published",
                        extra={
                            "event_id": str(envelope.event_id),
                            "source_id": envelope.source.source_id,
                            "topic": route.topic(),
                            "outcome": "PUBACK",
                        },
                    )
                    return
            if attempt < self._settings.publish_attempts:
                await asyncio.sleep(delay)
                delay *= 2
        raise BrokerUnavailable("MQTT publish did not receive PUBACK")

    async def close(self) -> None:
        if not self._started:
            return
        self._stopping = True
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()
        self._state = ConnectionState.STOPPED
        self._started = False
        self._stopping = False


class MqttIngestionWorker:
    """SUBACK-gated, bounded consumer that ACKs only after durable processing."""

    def __init__(
        self,
        settings: MqttConnectionSettings,
        processor: TelemetryMessageProcessor,
        *,
        client_id: str = "pigwatch-ingestion-v1",
        client: mqtt.Client | None = None,
    ) -> None:
        self._settings = settings
        self._processor = processor
        self._client = client or mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv5,
            manual_ack=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_connect_fail = self._on_connect_fail
        self._client.on_disconnect = self._on_disconnect
        self._client.on_subscribe = self._on_subscribe
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._state = ConnectionState.STOPPED
        self._connected = threading.Event()
        self._subscribed = threading.Event()
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._processing_semaphore: asyncio.Semaphore | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._stopping = False
        self._started = False
        self._saturated = False
        self._connection_count = 0
        self._subscription_count = 0
        self._pending_subscribe_mid: int | None = None
        self._pending: set[asyncio.Task[ProcessingResult | None]] = set()
        self._overflow_recovery_task: asyncio.Task[None] | None = None
        self._recovering_overflow = False
        self._active_count = 0

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def is_subscribed(self) -> bool:
        return self._subscribed.is_set()

    @property
    def is_saturated(self) -> bool:
        return self._saturated

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    @property
    def connection_count(self) -> int:
        """Return successful connections, including reconnects, for observability."""

        return self._connection_count

    @property
    def subscription_count(self) -> int:
        """Return successful SUBACKs, including reconnect confirmations."""

        return self._subscription_count

    @property
    def pending_count(self) -> int:
        """Return bounded received deliveries that are not durably settled."""

        return len(self._pending)

    @property
    def active_count(self) -> int:
        """Return deliveries currently inside the processing concurrency boundary."""

        return self._active_count

    def _refresh_ready(self) -> None:
        ready = (
            self._connected.is_set()
            and self._subscribed.is_set()
            and not self._saturated
            and not self._recovering_overflow
            and not self._stopping
        )
        if ready:
            self._ready.set()
        else:
            self._ready.clear()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        del userdata, flags, properties
        self._subscribed.clear()
        self._pending_subscribe_mid = None
        if _connection_failed(reason_code):
            self._state = ConnectionState.DISCONNECTED
            self._connected.clear()
            self._refresh_ready()
            return
        self._state = ConnectionState.SUBSCRIBING
        self._connection_count += 1
        self._connected.set()
        self._refresh_ready()
        result, message_id = client.subscribe(OBSERVATION_TOPIC_FILTER, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS or message_id is None:
            LOGGER.error(
                "mqtt_subscription_request_failed",
                extra={"broker_state": self._state.value},
            )
            return
        self._pending_subscribe_mid = message_id
        LOGGER.info("mqtt_consumer_connected", extra={"broker_state": self._state.value})

    def _on_subscribe(
        self,
        client: mqtt.Client,
        userdata: Any,
        message_id: int,
        reason_codes: list[ReasonCode],
        properties: Properties | None,
    ) -> None:
        del client, userdata, properties
        if message_id != self._pending_subscribe_mid:
            LOGGER.warning("mqtt_unexpected_suback", extra={"outcome": message_id})
            return
        granted_qos_one = bool(reason_codes) and all(
            not _connection_failed(reason_code) and reason_code.value == 1
            for reason_code in reason_codes
        )
        if not granted_qos_one:
            self._subscribed.clear()
            self._refresh_ready()
            LOGGER.error(
                "mqtt_subscription_rejected",
                extra={"broker_state": self._state.value},
            )
            return
        self._pending_subscribe_mid = None
        self._subscription_count += 1
        self._state = ConnectionState.CONNECTED
        self._recovering_overflow = False
        self._subscribed.set()
        self._refresh_ready()
        LOGGER.info("mqtt_subscription_established", extra={"broker_state": self._state.value})

    def _on_connect_fail(self, client: mqtt.Client, userdata: Any) -> None:
        del client, userdata
        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
        self._subscribed.clear()
        self._refresh_ready()
        LOGGER.warning("mqtt_consumer_connect_failed", extra={"broker_state": self._state.value})

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        del client, userdata, disconnect_flags, reason_code, properties
        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
        self._subscribed.clear()
        self._pending_subscribe_mid = None
        self._refresh_ready()
        if not self._stopping:
            LOGGER.warning(
                "mqtt_consumer_disconnected",
                extra={"broker_state": self._state.value},
            )

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        message: mqtt.MQTTMessage,
    ) -> None:
        del client, userdata
        if self._loop is None or self._stopping:
            return
        inbound = InboundMessage(
            topic=str(message.topic),
            payload=bytes(message.payload),
            message_id=message.mid,
            qos=message.qos,
        )
        self._loop.call_soon_threadsafe(self._schedule_message, inbound)

    def _schedule_message(self, message: InboundMessage) -> None:
        if self._stopping:
            return
        if len(self._pending) >= self._settings.receive_maximum:
            self._saturated = True
            self._recovering_overflow = True
            self._refresh_ready()
            LOGGER.error(
                "mqtt_ingestion_receive_limit_exceeded",
                extra={"outcome": self._settings.receive_maximum},
            )
            if self._overflow_recovery_task is None or self._overflow_recovery_task.done():
                self._overflow_recovery_task = asyncio.create_task(
                    self._recover_overflow_by_reconnecting(),
                    name="pigwatch-ingestion-overflow-recovery",
                )
            return
        task = asyncio.create_task(
            self._process_with_limit(message),
            name=f"pigwatch-ingestion-{message.message_id}",
        )
        self._pending.add(task)
        self._saturated = len(self._pending) >= self._settings.receive_maximum
        if self._saturated:
            LOGGER.warning(
                "mqtt_ingestion_saturated",
                extra={"outcome": len(self._pending)},
            )
        self._refresh_ready()
        task.add_done_callback(self._discard_task)

    def _discard_task(self, task: asyncio.Task[ProcessingResult | None]) -> None:
        self._pending.discard(task)
        self._saturated = len(self._pending) >= self._settings.receive_maximum
        self._refresh_ready()
        if not task.cancelled():
            exception = task.exception()
            if exception is not None:
                LOGGER.error(
                    "mqtt_processing_task_failed",
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

    def _release_current_delivery(self) -> None:
        """Release capacity once persistence, not task cleanup, has settled the delivery."""

        task = asyncio.current_task()
        if task is None:
            return
        self._pending.discard(task)
        self._saturated = len(self._pending) >= self._settings.receive_maximum
        self._refresh_ready()

    async def _recover_overflow_by_reconnecting(self) -> None:
        """Return unowned overflow deliveries to the broker's persistent session."""

        current_task = asyncio.current_task()
        try:
            reason_code = ReasonCode(PacketTypes.DISCONNECT, identifier=147)
            disconnect_result = self._client.disconnect(reasoncode=reason_code)
            if disconnect_result not in {mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_NO_CONN}:
                LOGGER.error(
                    "mqtt_ingestion_overflow_disconnect_failed",
                    extra={"outcome": disconnect_result},
                )

            # Existing application-owned work may settle durably while disconnected. Wait
            # until it has released its slots before restoring the persistent broker session.
            while self._pending and not self._stopping:
                await asyncio.sleep(0.01)
            while self._connected.is_set() and not self._stopping:
                await asyncio.sleep(0.01)
            if self._stopping:
                return

            # Paho documents that disconnect() terminates a loop_start() thread. Join that
            # thread before initializing a fresh asynchronous connection and starting exactly
            # one replacement network loop. That loop owns retry behavior and CONNACK/SUBACK.
            loop_stop_result = self._client.loop_stop()
            if loop_stop_result not in {mqtt.MQTT_ERR_SUCCESS, mqtt.MQTT_ERR_INVAL}:
                LOGGER.error(
                    "mqtt_ingestion_overflow_loop_stop_failed",
                    extra={"outcome": loop_stop_result},
                )
                return
            self._state = ConnectionState.CONNECTING
            self._connect_async()
            loop_start_result = self._client.loop_start()
            if loop_start_result != mqtt.MQTT_ERR_SUCCESS:
                self._state = ConnectionState.DISCONNECTED
                self._connected.clear()
                self._subscribed.clear()
                self._refresh_ready()
                LOGGER.error(
                    "mqtt_ingestion_overflow_loop_start_failed",
                    extra={"outcome": loop_start_result},
                )
        except (OSError, RuntimeError, ValueError) as exc:
            LOGGER.error(
                "mqtt_ingestion_overflow_reconnect_failed",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        finally:
            if self._overflow_recovery_task is current_task:
                self._overflow_recovery_task = None

    async def _process_with_limit(self, message: InboundMessage) -> ProcessingResult | None:
        semaphore = self._processing_semaphore
        if semaphore is None:
            raise RuntimeError("ingestion worker has not been started")
        async with semaphore:
            self._active_count += 1
            try:
                return await self._process_until_durable(message)
            finally:
                self._active_count -= 1

    async def _wait_for_retry_or_shutdown(self, delay: float) -> bool:
        shutdown_event = self._shutdown_event
        if shutdown_event is None:
            return self._stopping
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        except TimeoutError:
            return False
        return True

    async def _process_until_durable(self, message: InboundMessage) -> ProcessingResult | None:
        delay = self._settings.persistence_retry_initial_seconds
        while not self._stopping:
            try:
                result = await asyncio.wait_for(
                    self._processor.process(message.topic, message.payload),
                    timeout=self._settings.persistence_attempt_timeout_seconds,
                )
            except (PersistenceUnavailable, TimeoutError) as exc:
                jittered_delay = min(
                    delay * (1 + (message.message_id % 11) / 100),
                    self._settings.persistence_retry_max_seconds,
                )
                LOGGER.error(
                    "telemetry_database_unavailable",
                    extra={
                        "dependency": "postgresql",
                        "failure_kind": type(exc).__name__,
                        "retry_seconds": jittered_delay,
                    },
                )
                if await self._wait_for_retry_or_shutdown(jittered_delay):
                    return None
                delay = min(delay * 2, self._settings.persistence_retry_max_seconds)
                continue
            # Paho can receive the broker's replacement delivery from another thread while
            # ack() is executing. Release the durably settled slot first so capacity reflects
            # messages that still require application responsibility, not callback cleanup.
            self._release_current_delivery()
            acknowledgement = self._client.ack(message.message_id, message.qos)
            if acknowledgement != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.error(
                    "mqtt_ack_failed",
                    extra={"topic": message.topic, "outcome": acknowledgement},
                )
            return result
        return None

    def _connect_async(self) -> None:
        properties = Properties(PacketTypes.CONNECT)  # type: ignore[no-untyped-call]
        properties.SessionExpiryInterval = self._settings.session_expiry_seconds
        properties.ReceiveMaximum = self._settings.receive_maximum
        self._client.connect_async(
            self._settings.host,
            self._settings.port,
            self._settings.keepalive_seconds,
            clean_start=False,
            properties=properties,
        )

    async def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._processing_semaphore = asyncio.Semaphore(self._settings.processing_concurrency)
        self._shutdown_event = asyncio.Event()
        self._stopping = False
        self._saturated = False
        self._recovering_overflow = False
        self._connected.clear()
        self._subscribed.clear()
        self._ready.clear()
        self._state = ConnectionState.CONNECTING
        self._connect_async()
        self._client.loop_start()
        self._started = True

    async def wait_until_connected(self, timeout: float | None = None) -> bool:
        wait_for = timeout or self._settings.connect_timeout_seconds
        return await asyncio.to_thread(self._connected.wait, wait_for)

    async def wait_until_ready(self, timeout: float | None = None) -> bool:
        """Wait for connection, successful QoS 1 SUBACK and available ingestion capacity."""

        wait_for = timeout or self._settings.connect_timeout_seconds
        return await asyncio.to_thread(self._ready.wait, wait_for)

    async def close(self) -> None:
        if not self._started:
            return
        self._stopping = True
        self._ready.clear()
        self._subscribed.clear()
        if self._shutdown_event is not None:
            self._shutdown_event.set()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._settings.shutdown_timeout_seconds
        recovery_task = self._overflow_recovery_task
        if recovery_task is not None and not recovery_task.done():
            recovery_task.cancel()
            await asyncio.wait({recovery_task}, timeout=max(0.0, deadline - loop.time()))
        pending = set(self._pending)
        if pending and self._settings.shutdown_grace_seconds > 0:
            _, pending = await asyncio.wait(
                pending,
                timeout=self._settings.shutdown_grace_seconds,
            )
        for task in pending:
            task.cancel()
        remaining = max(0.0, deadline - loop.time())
        if pending and remaining > 0:
            _, pending = await asyncio.wait(pending, timeout=remaining)

        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()
        self._state = ConnectionState.STOPPED
        self._loop = None
        self._processing_semaphore = None
        self._shutdown_event = None
        self._overflow_recovery_task = None
        self._recovering_overflow = False
        self._started = False
        if pending:
            LOGGER.error("mqtt_shutdown_timeout", extra={"outcome": len(pending)})
            raise ShutdownTimeout(
                f"{len(pending)} ingestion task(s) exceeded the shutdown deadline"
            )
