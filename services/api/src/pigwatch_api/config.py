"""M1 application configuration loaded exclusively from runtime environment values."""

from __future__ import annotations

import os
from dataclasses import dataclass

from pigwatch_telemetry import MqttConnectionSettings


@dataclass(frozen=True, slots=True)
class ApplicationSettings:
    """Validated local runtime settings without logging connection secrets."""

    environment: str
    database_url: str
    mqtt: MqttConnectionSettings
    mqtt_client_id: str

    @classmethod
    def from_environment(cls) -> ApplicationSettings:
        """Build settings with loopback-safe clean-checkout development defaults."""

        return cls(
            environment=os.environ.get("PIGWATCH_ENVIRONMENT", "development"),
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql+asyncpg://pigwatch:pigwatch-local-only@127.0.0.1:5432/pigwatch",
            ),
            mqtt=MqttConnectionSettings(
                host=os.environ.get("MQTT_HOST", "127.0.0.1"),
                port=int(os.environ.get("MQTT_BROKER_PORT", "1883")),
            ),
            mqtt_client_id=os.environ.get("MQTT_CONSUMER_CLIENT_ID", "pigwatch-ingestion-v1"),
        )
