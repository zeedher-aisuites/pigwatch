"""PigWatch M1 telemetry contracts, transport, ingestion and persistence."""

from pigwatch_telemetry.ingestion import TelemetryProcessor, canonical_observation_fingerprint
from pigwatch_telemetry.logging import JsonLogFormatter, configure_structured_logging
from pigwatch_telemetry.models import (
    BrokerUnavailable,
    NormalizedObservation,
    PersistenceUnavailable,
    ProcessingResult,
    ProcessingStatus,
    RejectionCode,
    RejectionEvidence,
    ShutdownTimeout,
    StoredObservation,
    TelemetryValidationError,
)
from pigwatch_telemetry.mqtt import (
    ConnectionState,
    MqttConnectionSettings,
    MqttIngestionWorker,
    MqttTelemetryPublisher,
)
from pigwatch_telemetry.repository import (
    ObservationRepository,
    PostgresObservationRepository,
    metadata,
    observations,
    telemetry_rejections,
)
from pigwatch_telemetry.topics import (
    OBSERVATION_TOPIC_FILTER,
    ObservationCategory,
    ScopeKind,
    TopicRoute,
    parse_observation_topic,
)
from pigwatch_telemetry.validation import decode_observation

__all__ = [
    "OBSERVATION_TOPIC_FILTER",
    "BrokerUnavailable",
    "ConnectionState",
    "JsonLogFormatter",
    "MqttConnectionSettings",
    "MqttIngestionWorker",
    "MqttTelemetryPublisher",
    "NormalizedObservation",
    "ObservationCategory",
    "ObservationRepository",
    "PersistenceUnavailable",
    "PostgresObservationRepository",
    "ProcessingResult",
    "ProcessingStatus",
    "RejectionCode",
    "RejectionEvidence",
    "ScopeKind",
    "ShutdownTimeout",
    "StoredObservation",
    "TelemetryProcessor",
    "TelemetryValidationError",
    "TopicRoute",
    "canonical_observation_fingerprint",
    "configure_structured_logging",
    "decode_observation",
    "metadata",
    "observations",
    "parse_observation_topic",
    "telemetry_rejections",
]
