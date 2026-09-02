"""Common lifecycle contract for sources."""

from typing import Protocol

from pigwatch_schemas import SourceDescriptor


class SourceLifecycle(Protocol):
    """Lifecycle shared by sources without prescribing acquisition semantics."""

    @property
    def descriptor(self) -> SourceDescriptor:
        """Return immutable identity and provenance for this source."""
        ...

    async def open(self) -> None:
        """Acquire resources required by the source."""
        ...

    async def close(self) -> None:
        """Release resources; implementations should make this idempotent."""
        ...
