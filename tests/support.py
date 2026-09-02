"""Typed in-memory ports and static fixture loading for M1 tests."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pigwatch_schemas import ObservationEnvelopeV1, PayloadType, serialize_observation
from pigwatch_telemetry import (
    NormalizedObservation,
    PersistenceUnavailable,
    ProcessingResult,
    ProcessingStatus,
    RejectionCode,
    RejectionEvidence,
    StoredObservation,
)

FIXTURE_DIRECTORY = Path(__file__).parent / "fixtures" / "observations"


def load_observation_fixture(name: str) -> ObservationEnvelopeV1:
    """Load one immutable static observation contract fixture."""

    return ObservationEnvelopeV1.model_validate_json(
        (FIXTURE_DIRECTORY / f"{name}.json").read_bytes(),
        strict=True,
    )


class MemoryObservationRepository:
    """Behavioral in-memory implementation of the telemetry persistence port."""

    def __init__(self) -> None:
        self.observations: dict[UUID, NormalizedObservation] = {}
        self.rejections: list[RejectionEvidence] = []
        self.available = True
        self.closed = False

    async def persist(self, observation: NormalizedObservation) -> ProcessingResult:
        if not self.available:
            raise PersistenceUnavailable("test database unavailable")
        event_id = observation.envelope.event_id
        existing = self.observations.get(event_id)
        if existing is None:
            self.observations[event_id] = observation
            return ProcessingResult(ProcessingStatus.ACCEPTED, event_id)
        if existing.fingerprint == observation.fingerprint:
            return ProcessingResult(ProcessingStatus.DUPLICATE, event_id)
        return ProcessingResult(
            ProcessingStatus.REJECTED,
            event_id,
            RejectionCode.EVENT_ID_CONFLICT,
        )

    async def reject(self, evidence: RejectionEvidence) -> ProcessingResult:
        if not self.available:
            raise PersistenceUnavailable("test database unavailable")
        self.rejections.append(evidence)
        event_id: UUID | None = None
        if evidence.event_id_text is not None:
            try:
                event_id = UUID(evidence.event_id_text)
            except ValueError:
                pass
        return ProcessingResult(ProcessingStatus.REJECTED, event_id, evidence.code)

    async def get(self, event_id: UUID) -> StoredObservation | None:
        if not self.available:
            raise PersistenceUnavailable("test database unavailable")
        item = self.observations.get(event_id)
        if item is None:
            return None
        return StoredObservation(
            envelope=item.envelope,
            topic=item.topic,
            is_late=item.is_late,
            clock_skew_detected=item.clock_skew_detected,
            processing_outcome=ProcessingStatus.ACCEPTED,
        )

    async def query(
        self,
        *,
        source_id: str | None = None,
        event_time_from: datetime | None = None,
        event_time_to: datetime | None = None,
        payload_type: PayloadType | None = None,
        limit: int = 100,
    ) -> Sequence[StoredObservation]:
        if not self.available:
            raise PersistenceUnavailable("test database unavailable")
        stored = [await self.get(event_id) for event_id in self.observations]
        items = [item for item in stored if item is not None]
        if source_id is not None:
            items = [item for item in items if item.envelope.source.source_id == source_id]
        if event_time_from is not None:
            items = [item for item in items if item.envelope.event_time >= event_time_from]
        if event_time_to is not None:
            items = [item for item in items if item.envelope.event_time <= event_time_to]
        if payload_type is not None:
            items = [item for item in items if item.envelope.payload_type is payload_type]
        return sorted(items, key=lambda item: (item.envelope.event_time, item.envelope.event_id))[
            :limit
        ]

    async def healthcheck(self) -> bool:
        return self.available

    async def close(self) -> None:
        self.closed = True


def normalized_for_test(envelope: ObservationEnvelopeV1, topic: str) -> NormalizedObservation:
    """Create normalized evidence for repository/API tests without sensor behavior."""

    raw = serialize_observation(envelope)
    return NormalizedObservation(
        envelope=envelope,
        topic=topic,
        raw_message=raw,
        fingerprint=hashlib.sha256(raw).hexdigest(),
        is_late=False,
        clock_skew_detected=False,
    )
