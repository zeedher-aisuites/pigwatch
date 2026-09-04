"""Deterministic M2 environmental sensor source implementation."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import random
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from pigwatch_schemas import (
    SCHEMA_VERSION_V1,
    AmmoniaConcentrationPayload,
    ObservationEnvelopeV1,
    ObservationPayload,
    RelativeHumidityPayload,
    SourceDelivery,
    SourceDescriptor,
    SourceOrigin,
    TemperaturePayload,
    new_event_id,
)
from pigwatch_simulation.clock import SimulatorClock, SystemClock
from pigwatch_simulation.config import (
    EnvironmentalMeasurement,
    EnvironmentalSensorConfig,
    SimulationMode,
)
from pigwatch_telemetry import TopicRoute

LOGGER = logging.getLogger(__name__)
UNIX_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class ObservationPublisher(Protocol):
    """Narrow M1 publication port used by a sensor source."""

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None:
        """Publish one immutable wire envelope."""
        ...


class SimulatorState(StrEnum):
    """Observable lifecycle states for one environmental simulator."""

    CREATED = "CREATED"
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


def _timestamp_milliseconds(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("simulator clock must return a timezone-aware timestamp")
    delta = value.astimezone(UTC) - UNIX_EPOCH
    milliseconds = delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000
    if milliseconds < 0:
        raise ValueError("simulator clock must not predate the Unix epoch")
    return milliseconds


def _event_random_seed(config: EnvironmentalSensorConfig) -> int:
    material = f"pigwatch-m2-event-id\0{config.source_id}\0{config.seed}".encode()
    return int.from_bytes(hashlib.sha256(material).digest())


class EnvironmentalSensorSimulator:
    """Synthetic live environmental source with deterministic bounded values."""

    def __init__(
        self,
        config: EnvironmentalSensorConfig,
        *,
        clock: SimulatorClock | None = None,
    ) -> None:
        self.config = config
        self._clock = clock or SystemClock()
        self._descriptor = SourceDescriptor(
            source_id=config.source_id,
            origin=SourceOrigin.SYNTHETIC,
            delivery=SourceDelivery.LIVE,
        )
        self._value_random = random.Random(config.seed)
        self._event_random = random.Random(_event_random_seed(config))
        self._current_value: float | None = None
        self._state = SimulatorState.CREATED
        self._stop_requested = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._failure: Exception | None = None

    @property
    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    @property
    def route(self) -> TopicRoute:
        return self.config.route()

    @property
    def state(self) -> SimulatorState:
        return self._state

    @property
    def failure(self) -> Exception | None:
        return self._failure

    @property
    def task(self) -> asyncio.Task[None] | None:
        """Expose task identity for lifecycle verification, not scheduling control."""

        return self._task

    async def open(self) -> None:
        if self._state is not SimulatorState.CREATED:
            raise RuntimeError(f"cannot open simulator from {self._state.value}")
        self._state = SimulatorState.OPEN
        LOGGER.info(
            "sensor_simulator_opened",
            extra={
                "source_id": self.config.source_id,
                "measurement": self.config.measurement.value,
            },
        )

    def next_observation(self) -> ObservationEnvelopeV1:
        """Generate one genuine reading from the current deterministic state."""

        if self._state not in {SimulatorState.OPEN, SimulatorState.RUNNING}:
            raise RuntimeError(f"cannot generate observation from {self._state.value}")

        event_time = self._clock.now()
        timestamp_ms = _timestamp_milliseconds(event_time)
        event_time = event_time.astimezone(UTC)
        value = self._next_value()

        if self.config.measurement is EnvironmentalMeasurement.TEMPERATURE:
            payload: ObservationPayload = TemperaturePayload(value=value, unit="Cel")
        elif self.config.measurement is EnvironmentalMeasurement.RELATIVE_HUMIDITY:
            payload = RelativeHumidityPayload(value=value, unit="%")
        else:
            payload = AmmoniaConcentrationPayload(value=value, unit="[ppm]")

        envelope = ObservationEnvelopeV1(
            event_id=new_event_id(
                timestamp_ms=timestamp_ms,
                randomness=self._event_random.getrandbits(74),
            ),
            schema_version=SCHEMA_VERSION_V1,
            source=self._descriptor,
            event_time=event_time,
            replay_time=None,
            ingest_time=None,
            payload_type=self.config.measurement.payload_type,
            payload=payload,
            quality=None,
            trace=None,
        )
        LOGGER.debug(
            "sensor_observation_generated",
            extra={
                "event_id": str(envelope.event_id),
                "source_id": self.config.source_id,
                "measurement": self.config.measurement.value,
            },
        )
        return envelope

    def _next_value(self) -> float:
        if self._current_value is None:
            self._current_value = self.config.initial_value
            return self._current_value
        variation = self._value_random.uniform(
            -self.config.maximum_step,
            self.config.maximum_step,
        )
        self._current_value = min(
            self.config.maximum_value,
            max(self.config.minimum_value, self._current_value + variation),
        )
        return self._current_value

    async def start(self, publisher: ObservationPublisher) -> None:
        if self._state is not SimulatorState.OPEN:
            raise RuntimeError(f"cannot start simulator from {self._state.value}")
        if self._task is not None:
            raise RuntimeError("simulator already owns a generation task")
        self._state = SimulatorState.RUNNING
        self._task = asyncio.create_task(
            self._run(publisher),
            name=f"pigwatch-simulator-{self.config.source_id}",
        )

    async def _run(self, publisher: ObservationPublisher) -> None:
        LOGGER.info(
            "sensor_simulator_started",
            extra={
                "source_id": self.config.source_id,
                "measurement": self.config.measurement.value,
                "mode": self.config.mode.value,
            },
        )
        try:
            if self.config.mode is SimulationMode.STATIC:
                if not self._stop_requested.is_set():
                    await publisher.publish(self.route, self.next_observation())
            else:
                while not self._stop_requested.is_set():
                    await publisher.publish(self.route, self.next_observation())
                    if self._stop_requested.is_set():
                        break
                    await self._clock.wait(
                        self.config.cadence_seconds,
                        self._stop_requested,
                    )
            self._state = SimulatorState.STOPPED
        except asyncio.CancelledError:
            self._state = SimulatorState.STOPPED
            raise
        except Exception as exc:
            self._failure = exc
            self._state = SimulatorState.FAILED
            LOGGER.exception(
                "sensor_simulator_failed",
                extra={
                    "source_id": self.config.source_id,
                    "measurement": self.config.measurement.value,
                },
            )
            raise
        finally:
            LOGGER.info(
                "sensor_simulator_stopped",
                extra={
                    "source_id": self.config.source_id,
                    "measurement": self.config.measurement.value,
                    "outcome": self._state.value,
                },
            )

    async def wait(self) -> None:
        if self._task is None:
            raise RuntimeError("simulator has not been started")
        await asyncio.shield(self._task)

    async def stop(self) -> None:
        await self.close()

    async def close(self) -> None:
        if self._state is SimulatorState.CREATED:
            self._state = SimulatorState.STOPPED
            return
        if self._state is SimulatorState.OPEN:
            self._state = SimulatorState.STOPPED
            return
        if self._task is None or self._task.done():
            return

        self._state = SimulatorState.STOPPING
        self._stop_requested.set()
        try:
            await asyncio.shield(self._task)
        except Exception:
            # The source retains FAILED plus the original exception. wait()/runner.run()
            # owns propagation; close remains idempotent cleanup.
            return
