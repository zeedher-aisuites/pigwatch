"""Application lifecycle composition for the M1 modular-monolith telemetry path."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from pigwatch_api.config import ApplicationSettings
from pigwatch_telemetry import (
    MqttIngestionWorker,
    ObservationRepository,
    PostgresObservationRepository,
    TelemetryProcessor,
)


@dataclass(frozen=True, slots=True)
class DependencyReadiness:
    """Current status of dependencies required for useful M1 service."""

    postgresql: bool
    mqtt: bool

    @property
    def ready(self) -> bool:
        return self.postgresql and self.mqtt


class ApiRuntime(Protocol):
    """Runtime port used by HTTP routes and deterministic tests."""

    @property
    def repository(self) -> ObservationRepository: ...

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> DependencyReadiness: ...


class TelemetryRuntime:
    """Own the database pool and MQTT worker inside the existing API deployable."""

    def __init__(
        self,
        repository: ObservationRepository,
        worker: MqttIngestionWorker,
    ) -> None:
        self._repository = repository
        self._worker = worker

    @classmethod
    def build(cls, settings: ApplicationSettings) -> TelemetryRuntime:
        repository = PostgresObservationRepository(settings.database_url)
        processor = TelemetryProcessor(repository)
        worker = MqttIngestionWorker(
            settings.mqtt,
            processor,
            client_id=settings.mqtt_client_id,
        )
        return cls(repository, worker)

    @property
    def repository(self) -> ObservationRepository:
        return self._repository

    async def start(self) -> None:
        # Connection is asynchronous and non-fatal; readiness exposes transient broker failures.
        await self._worker.start()

    async def close(self) -> None:
        await self._worker.close()
        await self._repository.close()

    async def readiness(self) -> DependencyReadiness:
        database_ready, mqtt_ready = await asyncio.gather(
            self._repository.healthcheck(),
            asyncio.sleep(0, result=self._worker.is_ready),
        )
        return DependencyReadiness(postgresql=database_ready, mqtt=mqtt_ready)
