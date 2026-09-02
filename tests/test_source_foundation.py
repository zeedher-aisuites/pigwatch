"""Contract checks for the M0 source foundation."""

import asyncio

import pytest
from pydantic import ValidationError

from pigwatch_schemas import SourceDescriptor, SourceMode
from pigwatch_sources import AsyncSource


class StubSource:
    """Small structural implementation used to verify the protocol seam."""

    def __init__(self) -> None:
        self._descriptor = SourceDescriptor(source_id="stub-1", mode=SourceMode.SIMULATED)

    @property
    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    async def open(self) -> None:
        return None

    async def read(self) -> int:
        return 42

    async def close(self) -> None:
        return None


def test_source_modes_are_explicit_and_serializable() -> None:
    assert [mode.value for mode in SourceMode] == ["SIMULATED", "RECORDED", "LIVE"]
    descriptor = SourceDescriptor(source_id="camera-1", mode=SourceMode.RECORDED)

    assert descriptor.model_dump(mode="json") == {
        "source_id": "camera-1",
        "mode": "RECORDED",
    }


def test_source_descriptor_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SourceDescriptor.model_validate(
            {"source_id": "camera-1", "mode": SourceMode.LIVE, "secret": "unexpected"}
        )


def test_structural_async_source_contract() -> None:
    source = StubSource()

    assert isinstance(source, AsyncSource)
    assert asyncio.run(source.read()) == 42
