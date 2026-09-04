"""Minimal API retrieval behavior for accepted M1 observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from pigwatch_api.main import create_app
from pigwatch_api.runtime import DependencyReadiness
from pigwatch_telemetry import ProcessingStatus
from tests.support import (
    MemoryObservationRepository,
    load_observation_fixture,
    normalized_for_test,
)


@dataclass
class StubRuntime:
    repository: MemoryObservationRepository

    async def start(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def readiness(self) -> DependencyReadiness:
        return DependencyReadiness(postgresql=self.repository.available, mqtt=True)


async def request(runtime: StubRuntime, path: str) -> tuple[int, dict[str, object]]:
    app = create_app(lambda: runtime)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_get_observation_by_event_id() -> None:
    repository = MemoryObservationRepository()
    wire = load_observation_fixture("synthetic-recorded")
    accepted = wire.accepted_at(datetime(2026, 9, 2, 16, tzinfo=UTC))
    normalized = normalized_for_test(
        accepted,
        "pigwatch/v1/observations/site/test-site/fixture-synthetic-recorded/relative-humidity",
    )
    assert (await repository.persist(normalized)).status is ProcessingStatus.ACCEPTED

    status_code, body = await request(StubRuntime(repository), f"/v1/observations/{wire.event_id}")

    assert status_code == 200
    envelope = body["envelope"]
    assert isinstance(envelope, dict)
    assert envelope["source"] == {
        "source_id": "fixture-synthetic-recorded",
        "origin": "SYNTHETIC",
        "delivery": "RECORDED",
    }
    assert envelope["event_time"] == "2026-09-02T11:30:00Z"
    assert envelope["replay_time"] == "2026-09-02T15:30:00Z"
    assert envelope["ingest_time"] == "2026-09-02T16:00:00Z"


@pytest.mark.asyncio
async def test_query_filters_by_source_payload_and_time() -> None:
    repository = MemoryObservationRepository()
    for fixture_name in ("synthetic-live", "physical-live"):
        wire = load_observation_fixture(fixture_name)
        accepted = wire.accepted_at(datetime(2026, 9, 2, 16, tzinfo=UTC))
        await repository.persist(normalized_for_test(accepted, "test-topic"))

    path = (
        "/v1/observations?source_id=fixture-physical-live"
        "&payload_type=environment.ammonia_concentration"
        "&event_time_from=2026-09-02T12:00:30Z&event_time_to=2026-09-02T12:02:00Z"
    )
    status_code, body = await request(StubRuntime(repository), path)

    assert status_code == 200
    assert body["count"] == 1
    items = body["items"]
    assert isinstance(items, list)
    assert items[0]["envelope"]["source"]["source_id"] == "fixture-physical-live"


@pytest.mark.asyncio
async def test_query_can_return_newest_observations_without_changing_default_order() -> None:
    repository = MemoryObservationRepository()
    for fixture_name in ("physical-live", "synthetic-live"):
        wire = load_observation_fixture(fixture_name)
        accepted = wire.accepted_at(datetime(2026, 9, 2, 16, tzinfo=UTC))
        await repository.persist(normalized_for_test(accepted, "test-topic"))

    _, ascending = await request(StubRuntime(repository), "/v1/observations")
    _, descending = await request(StubRuntime(repository), "/v1/observations?order=desc")

    ascending_items = ascending["items"]
    descending_items = descending["items"]
    assert isinstance(ascending_items, list)
    assert isinstance(descending_items, list)
    assert ascending_items[0]["envelope"]["source"]["source_id"] == "fixture-synthetic-live"
    assert descending_items[0]["envelope"]["source"]["source_id"] == "fixture-physical-live"


@pytest.mark.asyncio
async def test_query_reverses_event_id_ties_with_the_requested_order() -> None:
    repository = MemoryObservationRepository()
    event_time = datetime(2026, 9, 2, 12, tzinfo=UTC)
    event_ids = [
        UUID("0199483f-0200-7000-8000-000000000001"),
        UUID("0199483f-0200-7000-8000-000000000002"),
    ]
    base = load_observation_fixture("synthetic-live")
    for event_id in reversed(event_ids):
        wire = base.model_copy(update={"event_id": event_id, "event_time": event_time})
        accepted = wire.accepted_at(datetime(2026, 9, 2, 16, tzinfo=UTC))
        await repository.persist(normalized_for_test(accepted, "test-topic"))

    _, ascending = await request(StubRuntime(repository), "/v1/observations?order=asc")
    _, descending = await request(StubRuntime(repository), "/v1/observations?order=desc")

    ascending_items = ascending["items"]
    descending_items = descending["items"]
    assert isinstance(ascending_items, list)
    assert isinstance(descending_items, list)
    assert [item["envelope"]["event_id"] for item in ascending_items] == [
        str(event_id) for event_id in event_ids
    ]
    assert [item["envelope"]["event_id"] for item in descending_items] == [
        str(event_id) for event_id in reversed(event_ids)
    ]


@pytest.mark.asyncio
async def test_retrieval_handles_not_found_invalid_range_and_database_failure() -> None:
    repository = MemoryObservationRepository()
    runtime = StubRuntime(repository)

    missing_status, _ = await request(
        runtime,
        "/v1/observations/019941c8-3800-7000-8000-000000000099",
    )
    invalid_status, _ = await request(
        runtime,
        "/v1/observations?event_time_from=2026-09-03T00:00:00Z&event_time_to=2026-09-02T00:00:00Z",
    )
    repository.available = False
    unavailable_status, unavailable = await request(runtime, "/v1/observations")

    assert missing_status == 404
    assert invalid_status == 422
    assert unavailable_status == 503
    assert unavailable["detail"] == "observation storage is unavailable"
