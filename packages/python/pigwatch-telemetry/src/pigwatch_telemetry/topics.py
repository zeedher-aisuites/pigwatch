"""Versioned MQTT observation topic construction and validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pigwatch_schemas import PayloadType
from pigwatch_telemetry.models import RejectionCode, TelemetryValidationError

OBSERVATION_TOPIC_FILTER = "pigwatch/v1/observations/+/+/+/+"

TopicSlug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,127}$")]


class ScopeKind(StrEnum):
    """Single routing scope represented in an M1 observation topic."""

    GLOBAL = "global"
    FARM = "farm"
    SITE = "site"
    BUILDING = "building"
    PEN = "pen"


class ObservationCategory(StrEnum):
    """Shallow MQTT routing categories mapped to typed payloads."""

    TEMPERATURE = "temperature"
    RELATIVE_HUMIDITY = "relative-humidity"
    AMMONIA_CONCENTRATION = "ammonia-concentration"


PAYLOAD_CATEGORY: dict[PayloadType, ObservationCategory] = {
    PayloadType.ENVIRONMENT_TEMPERATURE: ObservationCategory.TEMPERATURE,
    PayloadType.ENVIRONMENT_RELATIVE_HUMIDITY: ObservationCategory.RELATIVE_HUMIDITY,
    PayloadType.ENVIRONMENT_AMMONIA_CONCENTRATION: ObservationCategory.AMMONIA_CONCENTRATION,
}


class TopicRoute(BaseModel):
    """Validated routing values used to build or parse an observation topic."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_kind: ScopeKind
    scope_id: TopicSlug
    source_id: TopicSlug
    category: ObservationCategory

    def topic(self) -> str:
        """Return the stable versioned MQTT topic."""

        return (
            f"pigwatch/v1/observations/{self.scope_kind.value}/{self.scope_id}/"
            f"{self.source_id}/{self.category.value}"
        )


def parse_observation_topic(topic: str) -> TopicRoute:
    """Parse an exact observation topic or raise a safe semantic rejection."""

    segments = topic.split("/")
    if len(segments) != 7 or segments[:3] != ["pigwatch", "v1", "observations"]:
        raise TelemetryValidationError(
            RejectionCode.TOPIC_MISMATCH,
            "topic does not match the M1 observation taxonomy",
        )
    try:
        return TopicRoute(
            scope_kind=ScopeKind(segments[3]),
            scope_id=segments[4],
            source_id=segments[5],
            category=ObservationCategory(segments[6]),
        )
    except (ValidationError, ValueError) as exc:
        raise TelemetryValidationError(
            RejectionCode.TOPIC_MISMATCH,
            "topic contains an unsupported scope or invalid slug",
        ) from exc


def validate_route_matches_envelope(
    route: TopicRoute,
    *,
    source_id: str,
    payload_type: PayloadType,
) -> None:
    """Reject topics whose routing identity disagrees with the evidence envelope."""

    expected_category = PAYLOAD_CATEGORY[payload_type]
    if route.source_id != source_id or route.category is not expected_category:
        raise TelemetryValidationError(
            RejectionCode.TOPIC_MISMATCH,
            "topic source or category does not match the observation envelope",
        )
