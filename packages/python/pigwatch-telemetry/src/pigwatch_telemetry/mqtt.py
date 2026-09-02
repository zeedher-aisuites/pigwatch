"""Reusable MQTT v5 publisher and manually acknowledged ingestion worker."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from pigwatch_schemas import ObservationEnvelopeV1, serialize_observation
from pigwatch_telemetry.ingestion import TelemetryProcessor
from pigwatch_telemetry.models import BrokerUnavailable, PersistenceUnavailable, ProcessingResult
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


def _connection_failed(reason_code: Any) -> bool:
    return bool(getattr(reason_code, "is_failure", reason_code != 0))


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
    """Persistent-session MQTT consumer that ACKs only after durable processing."""

    def __init__(
        self,
        settings: MqttConnectionSettings,
        processor: TelemetryProcessor,
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
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._state = ConnectionState.STOPPED
        self._connected = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stopping = False
        self._started = False
        self._connection_count = 0
        self._pending: set[concurrent.futures.Future[ProcessingResult | None]] = set()
        self._pending_lock = threading.Lock()

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
        del userdata, flags, properties
        if _connection_failed(reason_code):
            self._state = ConnectionState.DISCONNECTED
            self._connected.clear()
            return
        result, _ = client.subscribe(OBSERVATION_TOPIC_FILTER, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            self._state = ConnectionState.DISCONNECTED
            self._connected.clear()
            LOGGER.error("mqtt_subscription_failed", extra={"broker_state": self._state.value})
            return
        self._state = ConnectionState.CONNECTED
        self._connection_count += 1
        self._connected.set()
        LOGGER.info("mqtt_consumer_connected", extra={"broker_state": self._state.value})

    def _on_connect_fail(self, client: mqtt.Client, userdata: Any) -> None:
        del client, userdata
        self._state = ConnectionState.DISCONNECTED
        self._connected.clear()
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
        del userdata
        if self._loop is None or self._stopping:
            return
        future = asyncio.run_coroutine_threadsafe(
            self._process_until_durable(client, message),
            self._loop,
        )
        with self._pending_lock:
            self._pending.add(future)
        future.add_done_callback(self._discard_future)

    def _discard_future(self, future: concurrent.futures.Future[ProcessingResult | None]) -> None:
        with self._pending_lock:
            self._pending.discard(future)
        if not future.cancelled():
            exception = future.exception()
            if exception is not None:
                LOGGER.error(
                    "mqtt_processing_task_failed",
                    exc_info=(type(exception), exception, exception.__traceback__),
                )

    async def _process_until_durable(
        self,
        client: mqtt.Client,
        message: mqtt.MQTTMessage,
    ) -> ProcessingResult | None:
        delay = self._settings.persistence_retry_initial_seconds
        while not self._stopping:
            try:
                result = await asyncio.wait_for(
                    self._processor.process(message.topic, bytes(message.payload)),
                    timeout=self._settings.persistence_attempt_timeout_seconds,
                )
            except (PersistenceUnavailable, TimeoutError) as exc:
                LOGGER.error(
                    "telemetry_database_unavailable",
                    extra={
                        "dependency": "postgresql",
                        "failure_kind": type(exc).__name__,
                        "retry_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self._settings.persistence_retry_max_seconds)
                continue
            acknowledgement = client.ack(message.mid, message.qos)
            if acknowledgement != mqtt.MQTT_ERR_SUCCESS:
                LOGGER.error(
                    "mqtt_ack_failed",
                    extra={"topic": message.topic, "outcome": acknowledgement},
                )
            return result
        return None

    async def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._stopping = False
        self._state = ConnectionState.CONNECTING
        properties = Properties(PacketTypes.CONNECT)  # type: ignore[no-untyped-call]
        properties.SessionExpiryInterval = self._settings.session_expiry_seconds
        self._client.connect_async(
            self._settings.host,
            self._settings.port,
            self._settings.keepalive_seconds,
            clean_start=False,
            properties=properties,
        )
        self._client.loop_start()
        self._started = True

    async def wait_until_connected(self, timeout: float | None = None) -> bool:
        wait_for = timeout or self._settings.connect_timeout_seconds
        return await asyncio.to_thread(self._connected.wait, wait_for)

    async def close(self) -> None:
        if not self._started:
            return
        self._stopping = True
        with self._pending_lock:
            pending = tuple(self._pending)
        for future in pending:
            future.cancel()
        self._client.disconnect()
        self._client.loop_stop()
        self._connected.clear()
        self._state = ConnectionState.STOPPED
        self._loop = None
        self._started = False
