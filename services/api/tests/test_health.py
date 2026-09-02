"""Tests for M0 API health probes."""

import asyncio

from httpx import ASGITransport, AsyncClient, Response

from pigwatch_api.main import app


async def get(path: str) -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_liveness() -> None:
    response = asyncio.run(get("/health/live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pigwatch-api"}


def test_readiness() -> None:
    response = asyncio.run(get("/health/ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "pigwatch-api"}
