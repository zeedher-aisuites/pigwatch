"""Common lifecycle contract for asynchronous sources."""

from typing import Protocol, TypeVar, runtime_checkable

from pigwatch_schemas import SourceDescriptor

SampleT_co = TypeVar("SampleT_co", covariant=True)


@runtime_checkable
class AsyncSource(Protocol[SampleT_co]):
    """Minimal contract shared by simulated, recorded, and live sources."""

    @property
    def descriptor(self) -> SourceDescriptor:
        """Return immutable identity and provenance for this source."""
        ...

    async def open(self) -> None:
        """Acquire resources needed to read samples."""
        ...

    async def read(self) -> SampleT_co:
        """Return the next capability-specific sample."""
        ...

    async def close(self) -> None:
        """Release resources; implementations should make this idempotent."""
        ...
