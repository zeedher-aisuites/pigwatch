"""Developer command-line entry point for the M2 sensor simulator."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from pigwatch_simulation.clock import SystemClock
from pigwatch_simulation.config import SimulatorConfiguration
from pigwatch_simulation.runner import MultiSourceSimulatorRunner
from pigwatch_simulation.simulator import EnvironmentalSensorSimulator
from pigwatch_telemetry import (
    BrokerUnavailable,
    MqttConnectionSettings,
    MqttTelemetryPublisher,
    configure_structured_logging,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path("configs/simulator.development.json")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pigwatch-simulator",
        description="Publish deterministic synthetic environmental observations through M1 MQTT.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(os.environ.get("PIGWATCH_SIMULATOR_CONFIG", DEFAULT_CONFIG_PATH)),
    )
    parser.add_argument(
        "--mqtt-host",
        default=os.environ.get("PIGWATCH_SIMULATOR_MQTT_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=os.environ.get("PIGWATCH_SIMULATOR_MQTT_PORT", "1883"),
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("PIGWATCH_SIMULATOR_CLIENT_ID", "pigwatch-simulator-v1"),
    )
    parser.add_argument(
        "--connect-timeout",
        type=float,
        default=os.environ.get("PIGWATCH_SIMULATOR_CONNECT_TIMEOUT", "5"),
    )
    parser.add_argument(
        "--publish-timeout",
        type=float,
        default=os.environ.get("PIGWATCH_SIMULATOR_PUBLISH_TIMEOUT", "5"),
    )
    parser.add_argument(
        "--publish-attempts",
        type=int,
        default=os.environ.get("PIGWATCH_SIMULATOR_PUBLISH_ATTEMPTS", "3"),
    )
    return parser


async def _run(args: argparse.Namespace) -> None:
    configuration = SimulatorConfiguration.from_json_file(args.config)
    settings = MqttConnectionSettings(
        host=args.mqtt_host,
        port=args.mqtt_port,
        connect_timeout_seconds=args.connect_timeout,
        publish_timeout_seconds=args.publish_timeout,
        publish_attempts=args.publish_attempts,
    )
    publisher = MqttTelemetryPublisher(settings, client_id=args.client_id)
    sources = tuple(
        EnvironmentalSensorSimulator(sensor, clock=SystemClock())
        for sensor in configuration.sensors
    )
    await MultiSourceSimulatorRunner(sources, publisher).run()


def main(argv: Sequence[str] | None = None) -> int:
    """Run configured sources and return an operator-meaningful process status."""

    configure_structured_logging()
    args = _parser().parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        LOGGER.info("sensor_simulator_interrupted")
        return 130
    except (BrokerUnavailable, FileNotFoundError, RuntimeError, ValidationError, ValueError):
        LOGGER.exception("sensor_simulator_command_failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
