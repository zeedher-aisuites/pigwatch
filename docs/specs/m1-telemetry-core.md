# M1 Telemetry Core Specification

## Status

Implementation specification for M1. The architecture decisions introduced here are recorded in
[ADR-0005](../adr/0005-telemetry-contract-delivery-and-storage.md), which is conceptually approved
by the Product Owner but remains `Proposed` until the final implementation fixes pass independent
verification.

## Purpose

M1 establishes the first real PigWatch data backbone. A valid observation can travel from a
reusable publisher through MQTT, validation and normalization into durable PostgreSQL storage and
then be retrieved programmatically. The path preserves evidence provenance and traceability while
making duplicates, invalid messages and dependency failures explicit.

## Scope

M1 includes:

- one versioned observation envelope and three typed scalar fixture payloads;
- deterministic MQTT serialization and a stable topic convention;
- a reusable MQTT publisher and an MQTT ingestion worker inside the existing API deployable;
- PostgreSQL migrations, idempotent persistence and minimal retrieval endpoints;
- rejection evidence, structured telemetry logs and dependency-aware readiness;
- unit, contract and PostgreSQL/MQTT integration tests; and
- local Docker Compose and CI validation of the full path.

## Explicit non-goals

M1 does not include source acquisition contracts, continuous sensor generation, simulation ground
truth, animals, cameras, thermal arrays, RFID, anomaly detection, analytics, charts, the Digital
Farm, alerts, LLMs, cloud deployment, production authentication, automatic unit conversion,
TimescaleDB, a schema registry or a producer outbox.

The scalar payloads are static contract fixtures. They do not implement M2 sensor behavior.

## Terminology

- **Observation:** what a source reports. It is neither simulation ground truth nor inferred state.
- **Wire envelope:** the producer-created MQTT document. Its required `ingest_time` is `null`.
- **Accepted envelope:** the validated envelope after PigWatch assigns `ingest_time` in UTC.
- **Replay time:** when recorded evidence was replayed into the telemetry path; it is distinct from
  both original occurrence and PigWatch acceptance.
- **Raw evidence:** the exact received MQTT bytes, bounded to 64 KiB.
- **Normalized observation:** validated columns and typed JSON derived without unit conversion.
- **Duplicate:** the same event ID, canonical envelope and normalized MQTT topic received more than
  once.
- **Identity conflict:** the same event ID received with a different canonical envelope or
  normalized MQTT topic.
- **Late:** accepted more than five minutes after `event_time`.
- **Out of order:** arrival order differs from event-time order. This is valid and is not rewritten.

## Observation envelope

Schema version `1.0` has this transport shape:

```json
{
  "event_id": "019941c8-3800-7000-8000-000000000001",
  "schema_version": "1.0",
  "source": {
    "source_id": "fixture-environment-1",
    "origin": "SYNTHETIC",
    "delivery": "RECORDED"
  },
  "event_time": "2026-09-02T12:00:00Z",
  "replay_time": "2026-09-02T15:30:00Z",
  "ingest_time": null,
  "payload_type": "environment.temperature",
  "payload": {
    "value": 21.5,
    "unit": "Cel"
  },
  "quality": {
    "status": "GOOD",
    "confidence": 0.98,
    "flags": []
  },
  "trace": {
    "correlation_id": "019941c8-3800-7000-8000-000000000010",
    "trace_id": "7f3f55a4443f48e48a63723c23c1276f"
  }
}
```

All fields shown are present. `quality` and `trace` may be `null`; their inner optional values are
not fabricated. Unknown fields are rejected. Serialization uses UTF-8 JSON with sorted keys and
compact separators, so the same model has deterministic bytes.

The producer must explicitly send `ingest_time: null`. Ingestion rejects producer-assigned ingest
times and stamps the accepted model immediately before persistence. This prevents a producer from
claiming when PigWatch accepted evidence. `RECORDED` delivery requires a timezone-aware
`replay_time`; `LIVE` delivery requires it to be absent or `null`. Serialization emits the field as
`null` for live evidence so the canonical shape remains deterministic.

## Payload model

M1 supports only these typed fixture payloads:

| `payload_type` | Payload | Allowed unit | Value rule |
| --- | --- | --- | --- |
| `environment.temperature` | scalar temperature | `Cel` | finite JSON number |
| `environment.relative_humidity` | scalar relative humidity | `%` | finite number from 0 through 100 |
| `environment.ammonia_concentration` | scalar NH3 concentration | `[ppm]` | finite number greater than or equal to 0 |

The top-level discriminator must match the typed payload. Strings, booleans, NaN and infinity are
not numbers. Arbitrary dictionaries and unknown payload types are rejected.

## Provenance

`source` reuses the accepted M0 `SourceDescriptor` contract:

- `SourceOrigin` is `SYNTHETIC` or `PHYSICAL`;
- `SourceDelivery` is `LIVE` or `RECORDED`.

The dimensions remain independent through serialization, topic validation, normalization,
persistence and retrieval. Recording or replay changes delivery, never origin. In particular,
`SYNTHETIC` + `RECORDED` must round-trip unchanged with its original `event_time`, explicit
`replay_time` and independently assigned `ingest_time`.

No observation field represents simulation ground truth. Ground truth has no M1 ingestion topic,
payload type, table or API.

## Event identity

`event_id` is a producer-generated UUIDv7 validated according to RFC 9562. UUIDv7 provides a large
random component, distributed uniqueness and time-sortable identifiers without deriving identity
solely from the timestamp. A producer creates the ID once before publication and reuses the same
envelope and ID for every retry or replay of that event.

PostgreSQL uses `event_id` as the observation primary key. A SHA-256 fingerprint of the normalized
topic plus canonical wire envelope distinguishes a legitimate redelivery from conflicting content
or routing scope that reuses an ID. This canonical fingerprint is not the forensic raw-message
SHA-256; the two hashes have distinct purposes.

## Time semantics

- `event_time` is when the source observed the value.
- `replay_time` is when recorded evidence entered replay; it is required only for `RECORDED`.
- `ingest_time` is when PigWatch accepted the message for processing.

All present timestamps are timezone-aware and normalized to UTC. Naive or malformed timestamps are
rejected. Arrival order never changes `event_time`, and neither replay nor ingestion overloads it.

An event older than five minutes at ingestion is accepted with `is_late=true`. There is no M1
maximum age because legitimate offline farms and recorded sources can be delayed. An event more
than five minutes in the future is accepted unchanged with `clock_skew_detected=true`. Both flags
are observable; neither falsifies evidence. Retrieval defaults to event-time order with event ID as
a deterministic tiebreaker.

## Schema versioning

`schema_version` is required and is the string `1.0` for M1. Decoding inspects this field before
model validation:

- missing versions receive `MISSING_SCHEMA_VERSION`;
- values other than `1.0` receive `UNSUPPORTED_SCHEMA_VERSION`;
- supported versions undergo full structural and semantic validation.

The original version is stored with every observation. Future compatible fields require a new
minor version only when old consumers can safely ignore them; incompatible shapes require a new
major version, a new typed parser and an overlap period. There is no silent downgrade or registry
in M1.

## Units

M1 stores explicit UCUM-style unit codes alongside every value. Each payload type has exactly one
allowed unit in M1. Invalid combinations are rejected, and ingestion performs no implicit
conversion. Supporting another unit requires a deliberate schema version and normalization policy.

## Quality metadata

Optional `quality` metadata contains:

- `status`: `GOOD`, `UNCERTAIN` or `BAD`;
- optional finite `confidence` from 0 through 1; and
- zero or more lower-case machine-readable flags.

Quality reports source evidence condition; it does not express diagnosis or ground truth.

## Trace and correlation metadata

Optional `trace` metadata contains a UUID correlation ID and/or a 32-character lower-case
hexadecimal trace ID. It supports cross-message and operational tracing without encoding routing or
domain state. Logs include IDs but not full raw payloads.

## MQTT topic taxonomy

Observation topics use:

```text
pigwatch/v1/observations/{scope_kind}/{scope_id}/{source_id}/{category}
```

`scope_kind` is one of `global`, `farm`, `site`, `building` or `pen`. Exactly one routing scope is
selected; the entire farm hierarchy is not copied into the topic. `scope_id`, `source_id` and
`category` are lower-case URL-safe slugs. M1 categories are `temperature`, `relative-humidity` and
`ammonia-concentration`.

Examples:

```text
pigwatch/v1/observations/site/north-barn/fixture-environment-1/temperature
pigwatch/v1/observations/pen/pen-12/fixture-environment-2/relative-humidity
pigwatch/v1/observations/global/all/fixture-environment-3/ammonia-concentration
```

The consumer subscribes to `pigwatch/v1/observations/+/+/+/+`. Source ID and category in the topic
must match the envelope. Location scope is meaningful routing evidence: the parsed route is
re-rendered to a normalized topic and participates in duplicate equivalence. A future location
contract may add independently validated envelope metadata without changing the topic depth.

Control, ground-truth, health and dead-letter data must not use observation topics.

## MQTT QoS, acknowledgement and delivery semantics

- Publishers and the consumer use MQTT v5 QoS 1 and never retain observation messages.
- A publisher waits for PUBACK and performs three bounded attempts with exponential delay while
  preserving the exact event ID and payload bytes.
- Mosquitto persistence and a named data volume are enabled for local M1 validation.
- Ingestion uses a stable client ID, a 24-hour persistent session and manual acknowledgement.
- Connection is not readiness. The consumer tracks the matching successful QoS 1 SUBACK and only
  then exposes telemetry readiness. Every reconnect re-establishes and confirms the subscription.
- The MQTT v5 CONNECT receive maximum bounds broker deliveries awaiting acknowledgement. A smaller
  application processing semaphore bounds concurrent PostgreSQL work; saturation degrades
  readiness and is logged.
- Application capacity counts deliveries that still require durable application responsibility.
  A durably settled slot is released immediately before its synchronous ACK handoff, independent
  of later task-callback cleanup, so a broker replacement delivery can take ownership safely.
- An unexpected delivery beyond the negotiated bound is never silently dropped. Ingestion marks
  itself unready, disconnects and waits for owned work to settle, joins the terminated Paho network
  loop, initializes a fresh asynchronous connection and starts exactly one replacement loop. The
  persistent session then redelivers unacknowledged work; readiness remains false until SUBACK.
- A valid message is acknowledged only after the PostgreSQL transaction commits.
- An invalid message is acknowledged only after its rejection record commits.
- A database failure leaves the message unacknowledged. Each persistence attempt has a 10-second
  ceiling so a connection stranded across an outage cannot block redelivery indefinitely; processing
  retries with exponential delay bounded between 1 and 30 seconds. Readiness reports the database
  failure.
- Disconnects change connection state, fail readiness and trigger Paho's bounded reconnect delay.
- Consumer restart with the same client ID resumes the broker session while it remains within the
  expiry period. Database idempotency makes redelivery safe.
- Graceful shutdown stops scheduling work, gives near-complete processing a bounded grace period,
  cancels remaining tasks, awaits their cleanup to a finite deadline and only then permits the
  repository to close. Unacknowledged work remains eligible for broker redelivery.

### Actual guarantee

The M1 broker-to-PostgreSQL at-least-once boundary begins only after the intended persistent
consumer subscription has received a successful SUBACK. Within that established subscription,
broker persistence, session expiry and storage limits still apply, and duplicates are collapsed
transactionally. A fresh broker can PUBACK a publication before any subscription exists; that
message is not queued for a future subscriber and is outside the guarantee.

M1 does **not** claim unconditional end-to-end at-least-once delivery from producer creation. There
is no durable producer outbox, so a producer crash before PUBACK or retry exhaustion can lose an
event. Broker disk loss, session expiry and PostgreSQL data loss are also outside the guarantee.
Operational producers must wait for API readiness, which includes successful SUBACK, before they
assume durable ingestion is available. PUBACK alone is not proof of a subscriber or database path.

## Ingestion and normalization

The processing sequence is:

```text
MQTT bytes
  -> size and UTF-8/JSON decoding
  -> recursive duplicate-key detection
  -> schema-version dispatch
  -> structural Pydantic validation
  -> topic/envelope semantic validation
  -> UTC normalization and ingestion timestamp
  -> canonical fingerprint
  -> PostgreSQL transaction
  -> processing outcome
  -> MQTT acknowledgement
```

Normalization changes timezone representation to UTC and extracts queryable columns. It does not
convert units, alter values, infer provenance, reorder events or create defaults.

## Persistence strategy

Migration `0001_m1_telemetry_core` creates:

### `observations`

- UUIDv7 `event_id` primary key;
- schema version, source ID, origin and delivery;
- event, optional replay and ingest timestamps;
- payload type, numeric value, unit and typed payload JSON;
- optional quality and trace JSON;
- normalized MQTT topic, exact raw message bytes and canonical envelope/topic fingerprint;
- `is_late`, `clock_skew_detected` and processing outcome.

Indexes support source plus event time, payload type plus event time and ingest time. Check
constraints defend the version, provenance, unit/type combinations and processing outcome in depth.

### `telemetry_rejections`

- generated rejection ID and received timestamp;
- topic, optional event ID text, stable error code and bounded diagnostic detail;
- raw bytes, SHA-256 and a truncation flag.

No TimescaleDB, partitioning or media storage is introduced. Schema changes use Alembic. Upgrades
run before application startup. The initial migration has an honest downgrade that drops M1 tables;
that operation is destructive and is for isolated development/test rollback only, never a data
preservation strategy.

## Raw versus normalized evidence

Accepted rows retain the exact received bytes once, alongside normalized query columns. This is
intentional bounded duplication for forensic comparison and schema-evolution debugging. A message
larger than 64 KiB is rejected; rejection evidence stores its first 64 KiB plus a hash and marks it
truncated. Logs never print raw payloads.

Raw evidence can contain farm telemetry and identifiers. Production access control, encryption,
retention and deletion policy must be designed before deployment. Local M1 data is disposable.

## Idempotency and duplicate handling

The observation primary key defines deduplication scope across all sources and time:

- first valid occurrence inserts one observation;
- same ID, canonical envelope and normalized topic returns `DUPLICATE` without another row;
- same ID with different canonical content or normalized topic creates an `EVENT_ID_CONFLICT`
  rejection and leaves the accepted row unchanged.

Insertion and conflict inspection occur in a PostgreSQL transaction. Duplicate MQTT delivery can
therefore never create duplicate durable observations. Global event-ID uniqueness does not change.
Conflict evidence stores SHA-256 of the exact raw MQTT bytes, never the canonical comparison
fingerprint.

## Late and out-of-order policy

All legitimate delayed observations are stored. `event_time`, `ingest_time`, lateness and clock-skew
flags remain truthful. No stream window, watermark, reorder buffer or timestamp rewrite exists in
M1. Queries order by event time unless the caller explicitly filters differently.

## Invalid-event handling

The consumer remains alive for malformed or semantically invalid messages. Rejections use stable
codes including:

- `MESSAGE_TOO_LARGE`, `MALFORMED_JSON`, `JSON_NESTING_TOO_DEEP`, `STRUCTURALLY_INVALID`;
- `DUPLICATE_JSON_KEY` for duplicate keys at any JSON object depth;
- `MISSING_EVENT_ID`, `INVALID_EVENT_ID`;
- `MISSING_SCHEMA_VERSION`, `UNSUPPORTED_SCHEMA_VERSION`;
- `MISSING_PROVENANCE`, `INVALID_ORIGIN`, `INVALID_DELIVERY`;
- `MISSING_TIMESTAMP`, `INVALID_TIMESTAMP`;
- `UNKNOWN_PAYLOAD_TYPE`, `INVALID_VALUE`, `INVALID_UNIT`;
- `TOPIC_MISMATCH` and `EVENT_ID_CONFLICT`.

No missing value, unit, provenance or timestamp is fabricated. Topic, event-ID text, diagnostic
detail and other database text are deterministically sanitized of non-printable characters and
bounded before insertion. Rejection evidence retains bounded raw bytes plus SHA-256 of the complete
raw message. Deterministic invalid input therefore commits once and is ACKed; dependency/persistence
outages remain unacknowledged and retry. Manual prevalidation checks primitive JSON types before
enum membership or UUID parsing, and malformed array/object values are always routed through the
same controlled durable-rejection path. Excessive nesting is handled at the JSON decode and typed
validation boundaries without recursively walking the malicious structure; parser recursion
failures become `JSON_NESTING_TOO_DEEP` and retain the original bounded raw evidence.

## Reconnect and restart behavior

The publisher and consumer expose connection and subscription state. Initial broker unavailability
does not kill the API process. The Paho network loop reconnects with delays from one through thirty
seconds, and readiness returns only after a successful SUBACK. Deliberate overflow recovery accounts
for Paho ending its threaded loop on `disconnect()`: the old thread is joined before `connect_async()`
and one new `loop_start()`. Shutdown prevents that restart once stopping begins and awaits task
cleanup before repository disposal; messages not acknowledged are eligible for broker redelivery.
Database failures retry in process and remain visible in readiness/logs.

## Query and retrieval

The API provides:

- `GET /v1/observations/{event_id}`;
- `GET /v1/observations` with optional `source_id`, event-time range and `payload_type`, plus a
  bounded result limit.

Responses return accepted envelopes and processing metadata. There are no analytics,
aggregations, charts or dashboard changes.

## Health and observability

- `GET /health/live` reports only that the API process is running.
- `GET /health/ready` checks `SELECT 1`, successful MQTT connection plus SUBACK, and ingestion
  saturation; it returns HTTP 503 until useful ingestion capacity is ready.
- Dependency loss does not terminate the process.

The Compose API health check uses readiness rather than liveness. Services that publish at startup
must depend on that ready state; they must not treat broker PUBACK as subscriber readiness.

Telemetry logs are single-line JSON with timestamp, level, event, and safe context such as event
ID, source ID, topic, outcome, rejection code and broker state. Database and broker failures are
logged without connection strings, passwords or raw payloads.

## Security assumptions

M1 is local-development only. PostgreSQL and anonymous MQTT host ports remain bound to loopback.
Compose credentials are non-secret local defaults, while `.env.example` uses placeholders. No cloud
service, public listener, authentication system or secret is added. Payload sizes and query limits
are bounded. Production MQTT authentication/TLS, API authorization, database encryption, evidence
retention and multi-tenant isolation remain future security work.

## Schema evolution principles

- Preserve stored version and raw evidence.
- Add typed parsers; never reinterpret old bytes as a new version.
- Prefer additive changes, explicit compatibility tests and overlap periods.
- Backfill with explicit migrations when required; do not mutate source origin.
- Treat event identity, provenance and original event time as immutable evidence.

## Acceptance criteria

M1 is acceptable when automated tests and a local Compose smoke test demonstrate:

1. version `1.0` validates and unknown versions reject explicitly;
2. all four origin/delivery combinations survive serialization, MQTT, storage and retrieval, with
   recorded evidence preserving event, replay and ingest times independently;
3. a valid observation completes publisher -> MQTT -> ingestion -> PostgreSQL -> query;
4. duplicate ID/content creates exactly one accepted row;
5. conflicting content or normalized routing scope for one ID rejects without overwriting evidence;
6. late and out-of-order events preserve both timestamps and flags;
7. malformed, incomplete, ambiguous-unit and unsupported messages reject without killing ingestion;
8. broker/database unavailability affects readiness and recovery behavior is tested;
9. pre-SUBACK publication loss, post-SUBACK delivery, consumer restart with unacknowledged work and
   MQTT reconnect behavior are covered;
10. a fresh PostgreSQL database migrates successfully;
11. logs expose safe processing context;
12. Docker images, Compose, Python, frontend and integration CI checks pass;
13. recursive duplicate JSON keys and pathological rejection metadata reject durably;
14. bounded processing concurrency and graceful shutdown are demonstrated;
15. container-valued invalid fields reject durably, ACK and do not poison the consumer;
16. ACK handoff cannot strand a replacement delivery at the receive limit;
17. excessive JSON nesting rejects durably without escaping as `RecursionError`;
18. deliberate overflow restarts exactly one Paho loop and restores SUBACK-gated redelivery;
19. no M2 sensor generator, dashboard product feature or LLM dependency exists; and
20. the working tree is clean after the review-ready commit.
