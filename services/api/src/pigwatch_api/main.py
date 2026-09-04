"""FastAPI application factory for M1 health and observation retrieval."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, Response, status
from pydantic import AwareDatetime, BaseModel, ConfigDict

from pigwatch_api.config import ApplicationSettings
from pigwatch_api.runtime import ApiRuntime, TelemetryRuntime
from pigwatch_schemas import PayloadType
from pigwatch_telemetry import (
    PersistenceUnavailable,
    StoredObservation,
    configure_structured_logging,
)


class HealthResponse(BaseModel):
    """Stable response for process liveness probes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"] = "ok"
    service: Literal["pigwatch-api"] = "pigwatch-api"


class DependencyStatus(BaseModel):
    """Dependency readiness without connection or credential details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    postgresql: bool
    mqtt: bool


class ReadinessResponse(BaseModel):
    """Useful-service readiness separated from process liveness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ready", "not_ready"]
    service: Literal["pigwatch-api"] = "pigwatch-api"
    dependencies: DependencyStatus


class ObservationListResponse(BaseModel):
    """Bounded observation query result without analytics or aggregation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[StoredObservation, ...]
    count: int


RuntimeFactory = Callable[[], ApiRuntime]


def create_app(runtime_factory: RuntimeFactory | None = None) -> FastAPI:
    """Create the API while deferring external connections to application lifespan."""

    def default_runtime_factory() -> ApiRuntime:
        configure_structured_logging()
        return TelemetryRuntime.build(ApplicationSettings.from_environment())

    selected_factory = runtime_factory or default_runtime_factory

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime = selected_factory()
        application.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.close()

    application = FastAPI(
        title="PigWatch API",
        summary="Livestock anomaly monitoring decision-support API",
        version="0.2.0",
        lifespan=lifespan,
    )

    def runtime(request: Request) -> ApiRuntime:
        return cast(ApiRuntime, request.app.state.runtime)

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def liveness() -> HealthResponse:
        return HealthResponse()

    @application.get("/health/ready", response_model=ReadinessResponse, tags=["health"])
    async def readiness(request: Request, response: Response) -> ReadinessResponse:
        dependencies = await runtime(request).readiness()
        if not dependencies.ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="ready" if dependencies.ready else "not_ready",
            dependencies=DependencyStatus(
                postgresql=dependencies.postgresql,
                mqtt=dependencies.mqtt,
            ),
        )

    @application.get(
        "/v1/observations/{event_id}",
        response_model=StoredObservation,
        tags=["observations"],
    )
    async def observation_by_id(event_id: UUID, request: Request) -> StoredObservation:
        try:
            observation = await runtime(request).repository.get(event_id)
        except PersistenceUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="observation storage is unavailable",
            ) from exc
        if observation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="observation not found"
            )
        return observation

    @application.get(
        "/v1/observations",
        response_model=ObservationListResponse,
        tags=["observations"],
    )
    async def observations_query(
        request: Request,
        source_id: str | None = None,
        event_time_from: AwareDatetime | None = None,
        event_time_to: AwareDatetime | None = None,
        payload_type: PayloadType | None = None,
        order: Literal["asc", "desc"] = "asc",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> ObservationListResponse:
        if event_time_from is not None and event_time_to is not None:
            if event_time_from > event_time_to:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="event_time_from must not be after event_time_to",
                )
        try:
            result = await runtime(request).repository.query(
                source_id=source_id,
                event_time_from=event_time_from,
                event_time_to=event_time_to,
                payload_type=payload_type,
                descending=order == "desc",
                limit=limit,
            )
        except PersistenceUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="observation storage is unavailable",
            ) from exc
        items = tuple(result)
        return ObservationListResponse(items=items, count=len(items))

    return application


app = create_app()
