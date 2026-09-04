"""Injectable clock boundary for deterministic simulator timing."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Protocol


class SimulatorClock(Protocol):
    """Time source and interruptible cadence wait used by environmental simulators."""

    def now(self) -> datetime:
        """Return the observation time."""
        ...

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        """Wait for a cadence or return when source shutdown is requested."""
        ...


class SystemClock:
    """Timezone-aware UTC clock for normal periodic operation."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    async def wait(self, seconds: float, stop_requested: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(stop_requested.wait(), timeout=seconds)
        except TimeoutError:
            return
