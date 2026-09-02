# ADR-0003: Telemetry transport and persistence direction

- Status: Accepted
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

Future sensor sources and consumers need decoupled transport, validation, replay, and historical queries. M0 needs a stable direction without prematurely implementing M1.

## Decision

Use MQTT as the near-real-time observation transport, Pydantic for versioned boundary validation, and PostgreSQL for normalized historical state and metadata. Treat delivery as at least once and design consumers for idempotency, late data, and out-of-order data. Store large media outside relational rows and reference it through metadata.

Operational telemetry—logs, metrics, and traces—is separate from livestock observation telemetry.

## Consequences

Local development requires MQTT and PostgreSQL, supplied by Docker Compose. M1 must define identifiers, topic taxonomy, QoS, retention, schema evolution, and failure semantics before application producers and consumers are added.

## Alternatives considered

- Direct synchronous source-to-API calls: rejected because they tightly couple producers and consumers and weaken replay behavior.
- PostgreSQL as both message bus and history: rejected because transport and durable query concerns differ.
- A larger streaming platform at M0: rejected because its operational cost is not yet justified.

## Follow-up

Resolve the open M1 items in a telemetry specification and ADR amendments or successors before implementing product data flow.
