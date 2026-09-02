"""Source identity and provenance vocabulary."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class SourceMode(StrEnum):
    """How a source's data entered PigWatch."""

    SIMULATED = "SIMULATED"
    RECORDED = "RECORDED"
    LIVE = "LIVE"


class SourceDescriptor(BaseModel):
    """Stable source identity available before sample schemas exist."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=1)
    mode: SourceMode
