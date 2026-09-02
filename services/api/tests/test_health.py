"""Tests for M1 liveness and dependency-aware readiness."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient

from pigwatch_api.main import create_app
from pigwatch_api.runtime import DependencyReadiness
from tests.support import MemoryObservationRepository


@dataclass
class StubRuntime:
    """Controllable API runtime without external connections."""

    repository: MemoryObservationRepository
    dependencies: DependencyReadiness
    started: bool = False
    closed: bool = False

    async def start(self) -> None:
        self.started = True

    async def close(self) -> None:
        self.closed = True

    async def readiness(self) -> DependencyReadiness:
        return self.dependencies


async def get(runtime: StubRuntime, path: str) -> tuple[int, dict[str, object]]:
    app = create_app(lambda: runtime)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(path)
    return response.status_code, response.json()


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_infrastructure_readiness() -> None:
    runtime = StubRuntime(
        MemoryObservationRepository(),
        DependencyReadiness(postgresql=False, mqtt=False),
    )

    status_code, body = await get(runtime, "/health/live")

    assert status_code == 200
    assert body == {"status": "ok", "service": "pigwatch-api"}
    assert runtime.started is True
    assert runtime.closed is True


@pytest.mark.asyncio
async def test_readiness_returns_200_only_when_both_dependencies_are_ready() -> None:
    runtime = StubRuntime(
        MemoryObservationRepository(),
        DependencyReadiness(postgresql=True, mqtt=True),
    )

    status_code, body = await get(runtime, "/health/ready")

    assert status_code == 200
    assert body == {
        "status": "ready",
        "service": "pigwatch-api",
        "dependencies": {"postgresql": True, "mqtt": True},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependencies",
    [
        DependencyReadiness(postgresql=False, mqtt=True),
        DependencyReadiness(postgresql=True, mqtt=False),
        DependencyReadiness(postgresql=False, mqtt=False),
    ],
)
async def test_readiness_returns_503_for_any_critical_dependency_failure(
    dependencies: DependencyReadiness,
) -> None:
    runtime = StubRuntime(MemoryObservationRepository(), dependencies)

    status_code, body = await get(runtime, "/health/ready")

    assert status_code == 503
    assert body["status"] == "not_ready"
    assert body["dependencies"] == {
        "postgresql": dependencies.postgresql,
        "mqtt": dependencies.mqtt,
    }
