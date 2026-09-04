"""Fresh-database migration and schema-drift integration checks."""

from __future__ import annotations

import asyncio
import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import create_async_engine


async def table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)

    def inspect_tables(connection: Connection) -> set[str]:
        return set(inspect(connection).get_table_names())

    async with engine.connect() as connection:
        result = await connection.run_sync(inspect_tables)
    await engine.dispose()
    return result


async def observation_column_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)

    def inspect_columns(connection: Connection) -> set[str]:
        return {str(column["name"]) for column in inspect(connection).get_columns("observations")}

    async with engine.connect() as connection:
        result = await connection.run_sync(inspect_columns)
    await engine.dispose()
    return result


@pytest.mark.integration
def test_migration_upgrades_fresh_database_and_matches_metadata(
    integration_database_url: str,
) -> None:
    os.environ["DATABASE_URL"] = integration_database_url
    config = Config("services/api/alembic.ini")

    command.downgrade(config, "base")
    assert asyncio.run(table_names(integration_database_url)).isdisjoint(
        {"observations", "telemetry_rejections"}
    )

    command.upgrade(config, "head")
    assert {"alembic_version", "observations", "telemetry_rejections"}.issubset(
        asyncio.run(table_names(integration_database_url))
    )
    assert "replay_time" in asyncio.run(observation_column_names(integration_database_url))
    command.check(config)
