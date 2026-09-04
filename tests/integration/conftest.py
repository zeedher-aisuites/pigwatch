"""Actual PostgreSQL and MQTT fixtures for M1 integration behavior."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import create_async_engine

from pigwatch_telemetry import (
    MqttConnectionSettings,
    PostgresObservationRepository,
    observations,
    telemetry_rejections,
)


@pytest.fixture(scope="session")
def integration_database_url() -> str:
    value = os.environ.get("PIGWATCH_TEST_DATABASE_URL")
    if value is None:
        pytest.skip("PIGWATCH_TEST_DATABASE_URL is required for integration tests")
    return value


@pytest.fixture(scope="session")
def mqtt_settings() -> MqttConnectionSettings:
    return MqttConnectionSettings(
        host=os.environ.get("PIGWATCH_TEST_MQTT_HOST", "127.0.0.1"),
        port=int(os.environ.get("PIGWATCH_TEST_MQTT_PORT", "1883")),
        connect_timeout_seconds=10,
        publish_timeout_seconds=10,
        publish_attempts=5,
    )


@pytest_asyncio.fixture
async def postgres_repository(
    integration_database_url: str,
) -> AsyncIterator[PostgresObservationRepository]:
    engine = create_async_engine(integration_database_url)
    async with engine.begin() as connection:
        await connection.execute(delete(telemetry_rejections))
        await connection.execute(delete(observations))
    await engine.dispose()

    repository = PostgresObservationRepository(integration_database_url)
    yield repository
    await repository.close()
