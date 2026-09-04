"""Telemetry decode, semantic validation, normalization and persistence pipeline."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pigwatch_schemas import serialize_observation
from pigwatch_telemetry.models import (
    LATE_THRESHOLD_SECONDS,
    MAX_MESSAGE_BYTES,
    NormalizedObservation,
    ProcessingResult,
    ProcessingStatus,
    RejectionEvidence,
    TelemetryValidationError,
)
from pigwatch_telemetry.repository import ObservationRepository
from pigwatch_telemetry.topics import parse_observation_topic, validate_route_matches_envelope
from pigwatch_telemetry.validation import decode_observation

LOGGER = logging.getLogger(__name__)
FINGERPRINT_DOMAIN = b"pigwatch-observation-v1\0"


def canonical_observation_fingerprint(*, topic: str, envelope_bytes: bytes) -> str:
    """Hash normalized routing scope and canonical wire content without ambiguity."""

    digest = hashlib.sha256()
    digest.update(FINGERPRINT_DOMAIN)
    digest.update(topic.encode("utf-8"))
    digest.update(b"\0")
    digest.update(envelope_bytes)
    return digest.hexdigest()


class TelemetryProcessor:
    """Process independent MQTT deliveries without owning broker lifecycle."""

    def __init__(
        self,
        repository: ObservationRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    async def process(self, topic: str, raw_message: bytes) -> ProcessingResult:
        received_at = self._clock()
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise ValueError("processor clock must return a timezone-aware timestamp")
        received_at = received_at.astimezone(UTC)

        try:
            route = parse_observation_topic(topic)
            wire_envelope = decode_observation(raw_message)
            validate_route_matches_envelope(
                route,
                source_id=wire_envelope.source.source_id,
                payload_type=wire_envelope.payload_type,
            )
        except TelemetryValidationError as exc:
            evidence_bytes = raw_message[:MAX_MESSAGE_BYTES]
            evidence = RejectionEvidence(
                received_at=received_at,
                topic=topic,
                event_id_text=exc.event_id_text,
                code=exc.code,
                detail=exc.detail,
                raw_message=evidence_bytes,
                raw_sha256=hashlib.sha256(raw_message).hexdigest(),
                raw_truncated=len(raw_message) > MAX_MESSAGE_BYTES,
            )
            result = await self.repository.reject(evidence)
            LOGGER.warning(
                "telemetry_rejected",
                extra={
                    "event_id": evidence.event_id_text,
                    "topic": evidence.topic,
                    "outcome": result.status.value,
                    "rejection_code": exc.code.value,
                },
            )
            return result

        accepted = wire_envelope.accepted_at(received_at)
        normalized_topic = route.topic()
        canonical_bytes = serialize_observation(wire_envelope)
        delay = received_at - accepted.event_time
        threshold = timedelta(seconds=LATE_THRESHOLD_SECONDS)
        observation = NormalizedObservation(
            envelope=accepted,
            topic=normalized_topic,
            raw_message=raw_message,
            fingerprint=canonical_observation_fingerprint(
                topic=normalized_topic,
                envelope_bytes=canonical_bytes,
            ),
            is_late=delay > threshold,
            clock_skew_detected=delay < -threshold,
        )
        result = await self.repository.persist(observation)
        log = LOGGER.warning if result.status is ProcessingStatus.REJECTED else LOGGER.info
        log(
            "telemetry_processed",
            extra={
                "event_id": str(accepted.event_id),
                "source_id": accepted.source.source_id,
                "topic": normalized_topic,
                "outcome": result.status.value,
                "rejection_code": result.rejection_code.value if result.rejection_code else None,
            },
        )
        return result
