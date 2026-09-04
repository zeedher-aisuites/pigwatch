"""Strict versioned configuration for M2 environmental sensor simulation."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator

from pigwatch_schemas import PayloadType
from pigwatch_telemetry import ObservationCategory, ScopeKind, TopicRoute

CONFIG_VERSION_V1 = "1.0"
FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
PositiveFiniteFloat = Annotated[StrictFloat, Field(gt=0, allow_inf_nan=False)]
NonNegativeFiniteFloat = Annotated[StrictFloat, Field(ge=0, allow_inf_nan=False)]
Seed = Annotated[StrictInt, Field(ge=0, lt=1 << 64)]


class EnvironmentalMeasurement(StrEnum):
    """Environmental measurements simulated in M2."""

    TEMPERATURE = "TEMPERATURE"
    RELATIVE_HUMIDITY = "RELATIVE_HUMIDITY"
    NH3 = "NH3"

    @property
    def payload_type(self) -> PayloadType:
        return {
            EnvironmentalMeasurement.TEMPERATURE: PayloadType.ENVIRONMENT_TEMPERATURE,
            EnvironmentalMeasurement.RELATIVE_HUMIDITY: (PayloadType.ENVIRONMENT_RELATIVE_HUMIDITY),
            EnvironmentalMeasurement.NH3: PayloadType.ENVIRONMENT_AMMONIA_CONCENTRATION,
        }[self]

    @property
    def category(self) -> ObservationCategory:
        return {
            EnvironmentalMeasurement.TEMPERATURE: ObservationCategory.TEMPERATURE,
            EnvironmentalMeasurement.RELATIVE_HUMIDITY: (ObservationCategory.RELATIVE_HUMIDITY),
            EnvironmentalMeasurement.NH3: ObservationCategory.AMMONIA_CONCENTRATION,
        }[self]


class SimulationMode(StrEnum):
    """The two intentionally small M2 execution modes."""

    STATIC = "STATIC"
    PERIODIC = "PERIODIC"


class EnvironmentalSensorConfig(BaseModel):
    """Validated immutable configuration for one independent simulated sensor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str
    measurement: EnvironmentalMeasurement
    mode: SimulationMode
    cadence_seconds: PositiveFiniteFloat
    initial_value: FiniteFloat
    minimum_value: FiniteFloat
    maximum_value: FiniteFloat
    maximum_step: NonNegativeFiniteFloat
    seed: Seed
    scope_kind: ScopeKind
    scope_id: str

    @model_validator(mode="after")
    def validate_simulation_contract(self) -> EnvironmentalSensorConfig:
        if self.minimum_value > self.maximum_value:
            raise ValueError("minimum_value must not exceed maximum_value")
        if not self.minimum_value <= self.initial_value <= self.maximum_value:
            raise ValueError("initial_value must be within the configured bounds")
        if self.measurement is EnvironmentalMeasurement.RELATIVE_HUMIDITY:
            if self.minimum_value < 0 or self.maximum_value > 100:
                raise ValueError("relative humidity bounds must be between 0 and 100")
        if self.measurement is EnvironmentalMeasurement.NH3 and self.minimum_value < 0:
            raise ValueError("NH3 bounds must be non-negative")

        # Reuse M1 route validation instead of creating a second slug contract.
        self.route()
        return self

    def route(self) -> TopicRoute:
        """Build the exact M1 route for this sensor."""

        return TopicRoute(
            scope_kind=self.scope_kind,
            scope_id=self.scope_id,
            source_id=self.source_id,
            category=self.measurement.category,
        )


class SimulatorConfiguration(BaseModel):
    """Versioned configuration for one local multi-source simulator run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    sensors: Annotated[tuple[EnvironmentalSensorConfig, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> SimulatorConfiguration:
        source_ids = [sensor.source_id for sensor in self.sensors]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("sensor source_id values must be unique")
        return self

    @classmethod
    def from_json_file(cls, path: Path) -> SimulatorConfiguration:
        """Load a strict configuration document without hidden environment merging."""

        return cls.model_validate_json(path.read_bytes(), strict=True)
