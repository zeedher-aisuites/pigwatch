"""Source identity and orthogonal provenance vocabulary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceOrigin(StrEnum):
    """Whether evidence ultimately originated from a synthetic or physical source."""

    SYNTHETIC = "SYNTHETIC"
    PHYSICAL = "PHYSICAL"


class SourceDelivery(StrEnum):
    """Whether evidence is delivered as it is produced or replayed from a recording."""

    LIVE = "LIVE"
    RECORDED = "RECORDED"


class SourceDescriptor(BaseModel):
    """Stable source identity available before sample schemas exist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    origin: SourceOrigin
    delivery: SourceDelivery
