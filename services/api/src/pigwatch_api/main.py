"""FastAPI application factory and M0 health endpoints."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Stable response for orchestrator health probes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"
    service: Literal["pigwatch-api"] = "pigwatch-api"


def create_app() -> FastAPI:
    """Create the HTTP application without starting external resources."""
    application = FastAPI(
        title="PigWatch API",
        summary="Livestock anomaly monitoring decision-support API",
        version="0.1.0",
    )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse()

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def readiness() -> HealthResponse:
        # M0 has no external runtime dependencies to gate readiness on.
        return HealthResponse()

    return application


app = create_app()
