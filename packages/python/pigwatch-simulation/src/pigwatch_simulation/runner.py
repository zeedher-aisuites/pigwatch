"""Small composition layer for concurrent M2 environmental sources."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from pigwatch_schemas import ObservationEnvelopeV1
from pigwatch_simulation.simulator import EnvironmentalSensorSimulator
from pigwatch_telemetry import TopicRoute

LOGGER = logging.getLogger(__name__)


class ManagedObservationPublisher(Protocol):
    """M1 publisher lifecycle required by the multi-source runner."""

    async def start(self) -> None: ...

    async def publish(self, route: TopicRoute, envelope: ObservationEnvelopeV1) -> None: ...

    async def close(self) -> None: ...


class MultiSourceSimulatorRunner:
    """Run independent sensor sources through one shared M1 publisher."""

    def __init__(
        self,
        sources: tuple[EnvironmentalSensorSimulator, ...],
        publisher: ManagedObservationPublisher,
    ) -> None:
        if not sources:
            raise ValueError("runner requires at least one simulator source")
        self._sources = sources
        self._publisher = publisher
        self._started = False
        self._closed = False

    @property
    def sources(self) -> tuple[EnvironmentalSensorSimulator, ...]:
        return self._sources

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("simulator runner has already started")
        if self._closed:
            raise RuntimeError("closed simulator runner cannot be started")

        opened: list[EnvironmentalSensorSimulator] = []
        try:
            await self._publisher.start()
            for source in self._sources:
                await source.open()
                opened.append(source)
            for source in self._sources:
                await source.start(self._publisher)
        except Exception:
            await asyncio.gather(*(source.close() for source in opened), return_exceptions=True)
            await self._publisher.close()
            self._closed = True
            raise

        self._started = True
        LOGGER.info("sensor_simulator_runner_started", extra={"source_count": len(self._sources)})

    async def wait(self) -> None:
        if not self._started:
            raise RuntimeError("simulator runner has not started")
        await asyncio.gather(*(source.wait() for source in self._sources))

    async def run(self) -> None:
        await self.start()
        try:
            await self.wait()
        finally:
            await self.close()

    async def stop(self) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        await asyncio.gather(*(source.close() for source in self._sources), return_exceptions=True)
        await self._publisher.close()
        self._closed = True
        LOGGER.info("sensor_simulator_runner_stopped", extra={"source_count": len(self._sources)})
