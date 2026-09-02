"""Fresh-broker regression for the explicit pre-SUBACK delivery boundary."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from pigwatch_schemas import new_event_id
from pigwatch_telemetry import (
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
    PostgresObservationRepository,
    TelemetryProcessor,
)
from tests.integration.test_10_telemetry_path import route_for, wait_until
from tests.support import load_observation_fixture


@pytest.mark.integration
@pytest.mark.asyncio
async def test_publication_before_first_subscription_is_outside_delivery_guarantee(
    postgres_repository: PostgresObservationRepository,
    mqtt_settings: MqttConnectionSettings,
) -> None:
    """PUBACK before a subscription must not be mistaken for durable ingestion."""

    publisher = MqttTelemetryPublisher(
        mqtt_settings,
        client_id=f"integration-pre-subscription-publisher-{uuid4()}",
    )
    pre_subscription = load_observation_fixture("synthetic-live").model_copy(
        update={"event_id": new_event_id()}
    )
    post_subscription = pre_subscription.model_copy(update={"event_id": new_event_id()})
    await publisher.start()
    assert await publisher.wait_until_connected(10)

    await publisher.publish(route_for(pre_subscription), pre_subscription)
    await asyncio.sleep(0.5)
    assert await postgres_repository.get(pre_subscription.event_id) is None

    worker = MqttIngestionWorker(
        mqtt_settings,
        TelemetryProcessor(postgres_repository),
        client_id=f"integration-first-subscription-{uuid4()}",
    )
    try:
        assert not worker.is_ready
        await worker.start()
        assert await worker.wait_until_ready(10)
        assert worker.is_subscribed

        await asyncio.sleep(0.5)
        assert await postgres_repository.get(pre_subscription.event_id) is None

        await publisher.publish(route_for(post_subscription), post_subscription)
        await wait_until(lambda: _is_persisted(postgres_repository, post_subscription.event_id))
        assert await postgres_repository.count(post_subscription.event_id) == 1
    finally:
        await worker.close()
        await publisher.close()


async def _is_persisted(
    repository: PostgresObservationRepository,
    event_id: UUID,
) -> bool:
    return await repository.get(event_id) is not None
