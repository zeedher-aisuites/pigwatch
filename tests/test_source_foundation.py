"""Meaningful contract checks for the M0 source foundation."""

import asyncio

import pytest
from pydantic import ValidationError

from pigwatch_schemas import SourceDelivery, SourceDescriptor, SourceOrigin
from pigwatch_sources import SourceLifecycle


class StubSource:
    """Stateful lifecycle implementation used by contract tests."""

    def __init__(self) -> None:
        self._descriptor = SourceDescriptor(
            source_id="stub-1",
            origin=SourceOrigin.SYNTHETIC,
            delivery=SourceDelivery.LIVE,
        )
        self.is_open = False
        self.open_count = 0
        self.close_count = 0

    @property
    def descriptor(self) -> SourceDescriptor:
        return self._descriptor

    async def open(self) -> None:
        self.is_open = True
        self.open_count += 1

    async def close(self) -> None:
        if not self.is_open:
            return
        self.is_open = False
        self.close_count += 1


def source_descriptor(source: SourceLifecycle) -> SourceDescriptor:
    """Require static compatibility with the shared lifecycle protocol."""

    return source.descriptor


STATICALLY_COMPATIBLE_SOURCE: SourceLifecycle = StubSource()


def test_source_provenance_dimensions_are_explicit_and_serializable() -> None:
    assert [origin.value for origin in SourceOrigin] == ["SYNTHETIC", "PHYSICAL"]
    assert [delivery.value for delivery in SourceDelivery] == ["LIVE", "RECORDED"]
    descriptor = SourceDescriptor(
        source_id="scenario-replay-1",
        origin=SourceOrigin.SYNTHETIC,
        delivery=SourceDelivery.RECORDED,
    )

    assert descriptor.model_dump(mode="json") == {
        "source_id": "scenario-replay-1",
        "origin": "SYNTHETIC",
        "delivery": "RECORDED",
    }


def test_physical_recording_remains_distinct_from_synthetic_recording() -> None:
    synthetic_replay = SourceDescriptor(
        source_id="scenario-replay-1",
        origin=SourceOrigin.SYNTHETIC,
        delivery=SourceDelivery.RECORDED,
    )
    physical_replay = SourceDescriptor(
        source_id="camera-replay-1",
        origin=SourceOrigin.PHYSICAL,
        delivery=SourceDelivery.RECORDED,
    )

    assert synthetic_replay.origin is SourceOrigin.SYNTHETIC
    assert physical_replay.origin is SourceOrigin.PHYSICAL
    assert synthetic_replay.delivery is physical_replay.delivery


def test_source_descriptor_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SourceDescriptor.model_validate(
            {
                "source_id": "camera-1",
                "origin": SourceOrigin.PHYSICAL,
                "delivery": SourceDelivery.LIVE,
                "secret": "unexpected",
            }
        )


def test_descriptor_is_stable_across_open_and_close_lifecycle() -> None:
    source = StubSource()
    descriptor = source_descriptor(source)

    asyncio.run(source.open())
    assert source.open_count == 1
    assert source.descriptor is descriptor

    asyncio.run(source.close())
    assert source.close_count == 1
    assert source.descriptor is descriptor


def test_close_is_idempotent() -> None:
    source = StubSource()

    asyncio.run(source.open())
    asyncio.run(source.close())
    asyncio.run(source.close())

    assert source.close_count == 1
