"""PostgreSQL schema and transactional telemetry repository."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    LargeBinary,
    MetaData,
    String,
    Table,
    Uuid,
    and_,
    func,
    insert,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from pigwatch_schemas import ObservationEnvelopeV1, PayloadType
from pigwatch_telemetry.models import (
    NormalizedObservation,
    PersistenceUnavailable,
    ProcessingResult,
    ProcessingStatus,
    RejectionCode,
    RejectionEvidence,
    StoredObservation,
)

metadata = MetaData()

observations = Table(
    "observations",
    metadata,
    # UUIDv7 is validated at the application boundary; PostgreSQL stores its 128 bits natively.
    Column("event_id", Uuid(as_uuid=True), primary_key=True),
    Column("schema_version", String(16), nullable=False),
    Column("source_id", String(128), nullable=False),
    Column("source_origin", String(16), nullable=False),
    Column("source_delivery", String(16), nullable=False),
    Column("event_time", DateTime(timezone=True), nullable=False),
    Column("replay_time", DateTime(timezone=True), nullable=True),
    Column("ingest_time", DateTime(timezone=True), nullable=False),
    Column("payload_type", String(64), nullable=False),
    Column("value", Float, nullable=False),
    Column("unit", String(16), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("quality", JSONB, nullable=True),
    Column("trace", JSONB, nullable=True),
    Column("topic", String(512), nullable=False),
    Column("raw_message", LargeBinary, nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("is_late", Boolean, nullable=False),
    Column("clock_skew_detected", Boolean, nullable=False),
    Column("processing_outcome", String(16), nullable=False),
    CheckConstraint("schema_version = '1.0'", name="ck_observations_schema_version"),
    CheckConstraint(
        "source_origin IN ('SYNTHETIC', 'PHYSICAL')",
        name="ck_observations_source_origin",
    ),
    CheckConstraint(
        "source_delivery IN ('LIVE', 'RECORDED')",
        name="ck_observations_source_delivery",
    ),
    CheckConstraint(
        "(source_delivery = 'RECORDED' AND replay_time IS NOT NULL) OR "
        "(source_delivery = 'LIVE' AND replay_time IS NULL)",
        name="ck_observations_replay_time",
    ),
    CheckConstraint(
        "processing_outcome = 'ACCEPTED'",
        name="ck_observations_processing_outcome",
    ),
    CheckConstraint(
        "(payload_type = 'environment.temperature' AND unit = 'Cel') OR "
        "(payload_type = 'environment.relative_humidity' AND unit = '%') OR "
        "(payload_type = 'environment.ammonia_concentration' AND unit = '[ppm]')",
        name="ck_observations_payload_unit",
    ),
)

Index("ix_observations_source_event_time", observations.c.source_id, observations.c.event_time)
Index("ix_observations_payload_event_time", observations.c.payload_type, observations.c.event_time)
Index("ix_observations_ingest_time", observations.c.ingest_time)

telemetry_rejections = Table(
    "telemetry_rejections",
    metadata,
    Column(
        "rejection_id",
        BigInteger,
        primary_key=True,
        autoincrement=True,
    ),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("topic", String(512), nullable=False),
    Column("event_id_text", String(128), nullable=True),
    Column("error_code", String(64), nullable=False),
    Column("error_detail", String(512), nullable=False),
    Column("raw_message", LargeBinary, nullable=False),
    Column("raw_sha256", String(64), nullable=False),
    Column("raw_truncated", Boolean, nullable=False),
)

Index("ix_telemetry_rejections_received_at", telemetry_rejections.c.received_at)
Index("ix_telemetry_rejections_error_code", telemetry_rejections.c.error_code)


class ObservationRepository(Protocol):
    """Persistence port required by ingestion and query boundaries."""

    async def persist(self, observation: NormalizedObservation) -> ProcessingResult: ...

    async def reject(self, evidence: RejectionEvidence) -> ProcessingResult: ...

    async def get(self, event_id: UUID) -> StoredObservation | None: ...

    async def query(
        self,
        *,
        source_id: str | None = None,
        event_time_from: datetime | None = None,
        event_time_to: datetime | None = None,
        payload_type: PayloadType | None = None,
        limit: int = 100,
    ) -> Sequence[StoredObservation]: ...

    async def healthcheck(self) -> bool: ...

    async def close(self) -> None: ...


def _row_to_stored(row: RowMapping) -> StoredObservation:
    envelope = ObservationEnvelopeV1.model_validate(
        {
            "event_id": row["event_id"],
            "schema_version": row["schema_version"],
            "source": {
                "source_id": row["source_id"],
                "origin": row["source_origin"],
                "delivery": row["source_delivery"],
            },
            "event_time": row["event_time"],
            "replay_time": row["replay_time"],
            "ingest_time": row["ingest_time"],
            "payload_type": row["payload_type"],
            "payload": row["payload"],
            "quality": row["quality"],
            "trace": row["trace"],
        }
    )
    return StoredObservation(
        envelope=envelope,
        topic=row["topic"],
        is_late=row["is_late"],
        clock_skew_detected=row["clock_skew_detected"],
        processing_outcome=ProcessingStatus(row["processing_outcome"]),
    )


class PostgresObservationRepository:
    """Async PostgreSQL implementation with transactional event-id idempotency."""

    def __init__(self, database_url: str, *, engine: AsyncEngine | None = None) -> None:
        self._engine = engine or create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_timeout=5,
            connect_args={"timeout": 5, "command_timeout": 10},
        )

    async def persist(self, observation: NormalizedObservation) -> ProcessingResult:
        envelope = observation.envelope
        payload = envelope.payload.model_dump(mode="json")
        values = {
            "event_id": envelope.event_id,
            "schema_version": envelope.schema_version,
            "source_id": envelope.source.source_id,
            "source_origin": envelope.source.origin.value,
            "source_delivery": envelope.source.delivery.value,
            "event_time": envelope.event_time,
            "replay_time": envelope.replay_time,
            "ingest_time": envelope.ingest_time,
            "payload_type": envelope.payload_type.value,
            "value": envelope.payload.value,
            "unit": envelope.payload.unit,
            "payload": payload,
            "quality": envelope.quality.model_dump(mode="json") if envelope.quality else None,
            "trace": envelope.trace.model_dump(mode="json") if envelope.trace else None,
            "topic": observation.topic,
            "raw_message": observation.raw_message,
            "fingerprint": observation.fingerprint,
            "is_late": observation.is_late,
            "clock_skew_detected": observation.clock_skew_detected,
            "processing_outcome": ProcessingStatus.ACCEPTED.value,
        }
        try:
            async with self._engine.begin() as connection:
                statement = (
                    postgres_insert(observations)
                    .values(**values)
                    .on_conflict_do_nothing(index_elements=[observations.c.event_id])
                    .returning(observations.c.event_id)
                )
                inserted = (await connection.execute(statement)).scalar_one_or_none()
                if inserted is not None:
                    return ProcessingResult(ProcessingStatus.ACCEPTED, envelope.event_id)

                fingerprint = (
                    await connection.execute(
                        select(observations.c.fingerprint).where(
                            observations.c.event_id == envelope.event_id
                        )
                    )
                ).scalar_one()
                if fingerprint == observation.fingerprint:
                    return ProcessingResult(ProcessingStatus.DUPLICATE, envelope.event_id)

                await connection.execute(
                    insert(telemetry_rejections).values(
                        received_at=envelope.ingest_time,
                        topic=observation.topic,
                        event_id_text=str(envelope.event_id),
                        error_code=RejectionCode.EVENT_ID_CONFLICT.value,
                        error_detail=(
                            "event_id already exists with a different canonical envelope "
                            "or normalized topic"
                        ),
                        raw_message=observation.raw_message,
                        raw_sha256=hashlib.sha256(observation.raw_message).hexdigest(),
                        raw_truncated=False,
                    )
                )
                return ProcessingResult(
                    ProcessingStatus.REJECTED,
                    envelope.event_id,
                    RejectionCode.EVENT_ID_CONFLICT,
                )
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database persistence failed") from exc

    async def reject(self, evidence: RejectionEvidence) -> ProcessingResult:
        try:
            async with self._engine.begin() as connection:
                await connection.execute(
                    insert(telemetry_rejections).values(
                        received_at=evidence.received_at,
                        topic=evidence.topic,
                        event_id_text=evidence.event_id_text,
                        error_code=evidence.code.value,
                        error_detail=evidence.detail,
                        raw_message=evidence.raw_message,
                        raw_sha256=evidence.raw_sha256,
                        raw_truncated=evidence.raw_truncated,
                    )
                )
            event_id: UUID | None = None
            if evidence.event_id_text is not None:
                try:
                    event_id = UUID(evidence.event_id_text)
                except ValueError:
                    pass
            return ProcessingResult(ProcessingStatus.REJECTED, event_id, evidence.code)
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database rejection persistence failed") from exc

    async def get(self, event_id: UUID) -> StoredObservation | None:
        try:
            async with self._engine.connect() as connection:
                row = (
                    (
                        await connection.execute(
                            select(observations).where(observations.c.event_id == event_id)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            return _row_to_stored(row) if row is not None else None
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database retrieval failed") from exc

    async def query(
        self,
        *,
        source_id: str | None = None,
        event_time_from: datetime | None = None,
        event_time_to: datetime | None = None,
        payload_type: PayloadType | None = None,
        limit: int = 100,
    ) -> Sequence[StoredObservation]:
        filters = []
        if source_id is not None:
            filters.append(observations.c.source_id == source_id)
        if event_time_from is not None:
            filters.append(observations.c.event_time >= event_time_from)
        if event_time_to is not None:
            filters.append(observations.c.event_time <= event_time_to)
        if payload_type is not None:
            filters.append(observations.c.payload_type == payload_type.value)
        statement = select(observations)
        if filters:
            statement = statement.where(and_(*filters))
        statement = statement.order_by(observations.c.event_time, observations.c.event_id).limit(
            limit
        )
        try:
            async with self._engine.connect() as connection:
                rows = (await connection.execute(statement)).mappings().all()
            return [_row_to_stored(row) for row in rows]
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database query failed") from exc

    async def healthcheck(self) -> bool:
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except (SQLAlchemyError, OSError):
            return False

    async def count(self, event_id: UUID) -> int:
        """Return accepted rows for one ID; exposed for integration contract tests."""

        try:
            async with self._engine.connect() as connection:
                value = await connection.scalar(
                    select(func.count())
                    .select_from(observations)
                    .where(observations.c.event_id == event_id)
                )
            return int(value or 0)
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database count failed") from exc

    async def rejection_count(self, code: RejectionCode | None = None) -> int:
        """Return rejection rows for integration and operational validation."""

        statement = select(func.count()).select_from(telemetry_rejections)
        if code is not None:
            statement = statement.where(telemetry_rejections.c.error_code == code.value)
        try:
            async with self._engine.connect() as connection:
                value = await connection.scalar(statement)
            return int(value or 0)
        except (SQLAlchemyError, OSError) as exc:
            raise PersistenceUnavailable("database rejection count failed") from exc

    async def close(self) -> None:
        await self._engine.dispose()
