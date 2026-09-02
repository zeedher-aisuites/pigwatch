# ADR-0005: Telemetry contract, delivery and storage

- Status: Proposed
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

Accepted ADR-0003 selected MQTT, Pydantic and PostgreSQL but deliberately left event identity,
topics, delivery guarantees, acknowledgements, deduplication, raw evidence and concrete persistence
semantics to M1. Those decisions affect shared contracts, reliability and the long-term data model,
so they require explicit review rather than silent implementation.

PigWatch must preserve independent source origin and delivery provenance, accept delayed evidence,
remain healthy around invalid messages and dependency outages, and avoid claiming a stronger
delivery guarantee than the implementation provides.

## Decision

Adopt the version `1.0` typed observation envelope specified in
[`m1-telemetry-core.md`](../specs/m1-telemetry-core.md). Use producer-generated UUIDv7 event IDs,
timezone-aware UTC timestamps, explicit UCUM-style units and orthogonal `SourceOrigin` plus
`SourceDelivery`. The wire document carries `ingest_time: null`; ingestion assigns the authoritative
value. Recorded delivery requires a distinct UTC `replay_time`; live delivery forbids it. Event,
replay and ingest time must never be overloaded.

Use the versioned topic convention
`pigwatch/v1/observations/{scope_kind}/{scope_id}/{source_id}/{category}`. Use MQTT v5 QoS 1,
persistent broker storage, a stable 24-hour consumer session and manual acknowledgement after the
PostgreSQL acceptance or rejection transaction commits. Publishers wait for PUBACK and retry a
bounded number of times without changing event identity. Connection alone is not readiness: the
consumer must receive a successful SUBACK for its intended QoS 1 subscription. Compose startup and
API readiness expose this boundary so producers can wait for useful ingestion.

Bound incoming work with the MQTT v5 receive maximum and a smaller application processing
semaphore. Saturation is observable and degrades readiness. Graceful shutdown stops new work,
allows a bounded grace period, cancels the remainder, awaits cleanup to a finite deadline and only
then allows the repository to be disposed.

Keep ingestion in the existing API deployable as a modular-monolith background component. Do not
introduce another operated service in M1.

Store accepted observations in one normalized PostgreSQL table keyed by event ID, with exact
bounded raw message bytes and a canonical fingerprint in the same row. Store invalid evidence in a
separate rejection table. Duplicate ID/content is a successful no-op; reused IDs with different
content or normalized MQTT routing scope are explicit conflicts. The canonical duplicate
fingerprint combines the normalized topic and canonical envelope. Its purpose is distinct from
`raw_sha256`, which always hashes exact received bytes. Retain truthful event, replay and ingest
timestamps and flag lateness or clock skew without reordering evidence.

Before inserting a rejection, deterministically sanitize and bound topic, event-ID text and
diagnostic detail. Retain bounded raw bytes plus SHA-256 of the complete raw message. Deterministic
invalid input, including recursive duplicate JSON keys and pathological metadata, must commit and
ACK rather than enter a poison retry loop.

The actual broker-to-database at-least-once path begins only after successful SUBACK establishes the
intended persistent consumer subscription, and remains subject to configured broker persistence,
session and storage limits. Publication before the first subscription can receive PUBACK and still
be lost to that future consumer. M1 does not claim unconditional producer-to-database at-least-once
delivery because it has no durable producer outbox.

Use SQLAlchemy's asynchronous PostgreSQL support and Alembic migrations. PostgreSQL remains the only
data platform; do not add TimescaleDB or a schema registry.

## Consequences

Stable IDs and transactional uniqueness make QoS 1 redelivery safe. Manual acknowledgement ties
broker progress to durable processing, while rejection persistence keeps malformed evidence
observable. Exact bounded raw bytes support forensic comparison and future version migration.

The API process now depends on PostgreSQL, MQTT connection, confirmed subscription and available
bounded ingestion capacity for readiness, but not liveness. Its background consumer adds lifecycle,
backpressure, reconnect and shutdown complexity. Raw evidence increases storage and security
responsibility. A producer can lose an event before the first subscription, before broker
acknowledgement or after retry exhaustion; a future milestone must add an outbox or edge buffer if
those gaps are unacceptable.

The observation table and envelope become long-lived compatibility surfaces. Changes require
versioned contracts, migrations and explicit architecture review.

## Alternatives considered

- MQTT QoS 0: rejected because loss during ordinary disconnects is inappropriate for telemetry.
- MQTT QoS 2: rejected because its additional handshake does not replace database idempotency or a
  producer outbox, while QoS 1 plus UUID deduplication meets M1 needs.
- Automatic MQTT acknowledgement on callback receipt: rejected because a process crash before the
  database commit would silently lose accepted broker work.
- A separate ingestion microservice: rejected because M1 has no scaling, deployment or ownership
  evidence that outweighs modular-monolith simplicity.
- PostgreSQL as the transport: rejected by ADR-0003 and unsuitable for the source/broker boundary.
- Store only normalized data: rejected because it weakens forensic traceability and schema-evolution
  debugging.
- Store raw data only: rejected because every query would require reparsing and validation.
- One raw-message row per delivery attempt: rejected because QoS redelivery would amplify storage
  without improving accepted evidence identity.
- UUIDv4: viable for uniqueness, but UUIDv7 is preferred because the stack validates it cleanly and
  it improves operational ordering without making timestamps the sole identity source.
- TimescaleDB or a schema registry: deferred because M1 scale and version count do not justify them.

## Follow-up

- Product Owner review is required before this ADR becomes `Accepted`.
- Define production authentication, TLS, authorization, evidence retention, backup and recovery
  before any non-local deployment.
- Reassess a durable producer outbox or edge buffer when real source reliability requirements are
  known.
- Reassess partitioning and time-series extensions using measured volume and query evidence.
