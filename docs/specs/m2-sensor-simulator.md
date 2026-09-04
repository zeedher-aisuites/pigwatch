# M2 Sensor Simulator Specification

## Status

Implementation specification for M2. This milestone uses the accepted M0 source lifecycle and M1
telemetry contracts without changing their public schemas or architectural decisions.

## Objective

M2 provides deterministic synthetic environmental sensor sources for development, demonstration,
and infrastructure testing. Generated observations travel through the existing M1 publisher,
MQTT ingestion, validation, PostgreSQL persistence, and retrieval path. The simulator never writes
to PostgreSQL or invokes ingestion internals.

The generated trajectories are transparent infrastructure test signals. They are not calibrated
farm models, veterinary thresholds, animal physiology, health judgments, or disease labels.

## Scope

M2 includes:

- reusable synthetic environmental sensor sources for air temperature, relative humidity, and
  ammonia concentration (NH3);
- deterministic bounded-random-walk generation with injectable time;
- static one-observation and continuous periodic modes;
- typed, versionable configuration and centralized development profiles;
- a small concurrent runner and command-line entry point;
- publication exclusively through the M1 MQTT publisher; and
- unit, contract, and real MQTT/PostgreSQL integration tests.

## Non-goals

M2 does not include animals, animal physiology, health or disease state, ground-truth labels,
feeding, drinking, weight, movement, behavior, cameras, computer vision, RFID, thermal imaging,
tracking, sensor fusion, anomaly detection, health scores, alerts, dashboards, the Digital Farm,
LLMs, RAG, prediction, real hardware adapters, a general scheduler, a database-backed simulator
configuration system, or production deployment guarantees.

M2 does not implement recorded replay. The accepted M1 `SYNTHETIC` + `RECORDED` fixtures remain
valid, but replay scheduling is outside this simulator's runtime behavior.

## Contracts and component boundary

`EnvironmentalSensorSimulator` is an M2 capability adapter in `pigwatch-simulation`. It conforms
structurally to the M0 `SourceLifecycle` contract and adds environmental acquisition behavior owned
by M2. The common lifecycle contract is not modified.

The composition boundary is:

```text
EnvironmentalSensorSimulator
  -> MqttTelemetryPublisher
  -> MQTT v5 QoS 1 topic
  -> MqttIngestionWorker
  -> M1 validation and normalization
  -> PostgreSQL observations
  -> existing retrieval API
```

No simulator-specific table or product API is introduced.

## Simulator lifecycle

A simulator has explicit `CREATED`, `OPEN`, `RUNNING`, `STOPPING`, `STOPPED`, and `FAILED` states.

- `open()` validates the transition from `CREATED` and exposes the immutable descriptor.
- `start()` requires `OPEN`, creates exactly one task, and rejects a second start.
- a static source publishes one observation and stops;
- a periodic source publishes until stop is requested or publication/generation fails;
- `stop()` and `close()` request shutdown and wait for the owned task; repeated close calls are
  safe; and
- an unexpected generation or publication failure is logged, retained as the source failure, and
  transitions the source to `FAILED` rather than being swallowed.

The simulator owns no threads or timer handles. The runner closes every source before closing the
shared publisher. After shutdown, no simulator task remains active.

## Configuration model

Configuration schema version `1.0` is a strict JSON document containing one or more sensor
configurations. Unknown fields are rejected. Each sensor declares:

- `source_id`: M1-compatible lower-case topic slug;
- `measurement`: `TEMPERATURE`, `RELATIVE_HUMIDITY`, or `NH3`;
- `mode`: `STATIC` or `PERIODIC`;
- `cadence_seconds`: finite positive delay between successful periodic publications;
- `initial_value`: first generated value;
- `minimum_value` and `maximum_value`: inclusive simulation bounds;
- `maximum_step`: finite non-negative magnitude of one random-walk step;
- `seed`: integer from zero through 2^64 - 1;
- `scope_kind`: one accepted M1 routing scope; and
- `scope_id`: M1-compatible routing slug.

The configuration rejects empty sensor collections, duplicate source IDs, non-finite numbers,
invalid bounds, initial values outside bounds, invalid routing values, relative-humidity bounds
outside 0 through 100, and negative ammonia bounds. Temperature has no simulator-imposed clinical
range; all configured numbers must still be finite and M1-valid.

MQTT connection settings independently require every timeout, delay, keepalive, session-expiry,
and shutdown duration to be finite and greater than zero. This reusable boundary applies to CLI
overrides as well as direct construction and rejects invalid values before any network resource is
created.

The repository contains a versioned development configuration with one source for each supported
measurement. Its values are plausible test ranges only and must not be interpreted as healthy or
unhealthy thresholds. Defaults are centralized and may be replaced with another validated JSON
configuration.

## Supported measurements and units

M2 uses the exact M1 payload types and units:

| Measurement | M1 payload type | Unit |
| --- | --- | --- |
| Air temperature | `environment.temperature` | `Cel` |
| Relative humidity | `environment.relative_humidity` | `%` |
| NH3 concentration | `environment.ammonia_concentration` | `[ppm]` |

There is no unit conversion and no new observation payload type.

## Value generation and bounds

The first observation uses `initial_value`. Each later value draws a normalized source-local sample
`u` from `[0, 1)`, derives the signed sample `2u - 1`, and computes:

```text
delta = (2u - 1) * maximum_step
next = clamp(previous_value + delta, minimum_value, maximum_value)
```

The pseudorandom generator is local to one source and seeded from its configuration. Sources do
not share random state. Generated floats pass through the M1 typed payload constructor, which
provides a second validation boundary. No NaN or infinity can be configured or emitted.

The normalized sample avoids constructing a `2 * maximum_step` endpoint span. Candidate addition
and clamping use an exact representation of the participating finite floats, so valid values near
the IEEE-754 finite limits do not overflow during generation. The emitted representable value is
always within the configured bounds and its actual step is at most `maximum_step`; if rounding
offers no valid representable movement for an edge case, the previous value is retained.

This bounded random walk is deliberately simple and is not a scientific model of a pig farm,
sensor drift, environmental control, or animal response.

## Determinism and seed semantics

For a fixed configuration, seed, source identity, generation-call order, and injected clock, the
value sequence, timestamps, UUIDv7 event IDs, envelopes, routes, and serialized M1 bytes are
identical.

Value randomness uses a source-local generator seeded by `seed`. Event-identity randomness uses a
separate source-local generator deterministically derived from `seed` and `source_id`. Separating
the streams prevents event-ID creation from changing the value sequence and prevents two source
identities with the same seed and timestamp from intentionally producing the same ID sequence.

Re-running an identical deterministic fixture clock intentionally recreates identical events. With
the normal system clock, new runs have new UUIDv7 timestamp components.

## Clock and timestamp semantics

The source depends on an injectable clock with two operations: return the current time and wait for
a cadence or stop request. The production clock uses timezone-aware UTC system time. Tests use
controlled clocks and never require long sleeps.

For every generated observation:

- `event_time` is the clock instant at generation and is normalized to UTC;
- the UUIDv7 timestamp component uses that same instant at millisecond precision;
- `replay_time` is null because generated runtime delivery is live; and
- `ingest_time` is null on publication and remains assigned only by M1 ingestion.

Naive clock values fail explicitly. The simulator never modifies M1 ingest-time semantics.

## Source identity and provenance

Each source exposes a stable `SourceDescriptor` built from its configured `source_id`. All newly
generated M2 runtime observations are always:

```text
origin = SYNTHETIC
delivery = LIVE
```

The configuration cannot override those values. `replay_time` is therefore null. M2 does not put
simulation ground truth into an observation, MQTT topic, table, or retrieval response.

## Event identity and retry behavior

Every call that represents a genuine new reading constructs one valid UUIDv7 event ID before
publication. The completed immutable envelope is handed once to the M1 publisher. M1 serializes it
once and reuses the exact bytes and event ID for all bounded PUBACK attempts. The simulator does not
wrap the publisher in a second retry loop and does not generate the next reading until the current
publication succeeds.

If publisher attempts are exhausted, the source fails with that event unresolved; it does not
fabricate success or silently advance. MQTT redelivery or an explicit repeat of the same envelope
is collapsed by M1's topic-aware PostgreSQL idempotency.

## Static mode

`STATIC` publishes exactly one deterministic reading without a wall-clock loop and then stops. It
is intended for tests, smoke checks, demos, and deterministic fixtures. `cadence_seconds` remains
validated for a uniform versioned configuration shape but is not awaited.

## Periodic mode and cadence

`PERIODIC` publishes immediately after start. After each successful publication, it waits for the
configured cadence unless stopped. This is fixed-delay scheduling: publication duration adds to
the interval, missed timing is skipped, and the simulator never creates catch-up bursts.

One source owns at most one generation task. It never overlaps its own publications and never
accumulates timer tasks. Different sources may publish concurrently through the shared M1
publisher.

## Graceful stop

A stop request interrupts a cadence wait immediately. If a publication is already in progress,
the simulator allows the M1 publisher's bounded operation to settle, then stops without generating
another observation. This preserves publisher ownership of MQTT retry/reconnect behavior and avoids
claiming that a cancelled publish succeeded. Publisher timeout and retry limits bound that wait.

## Multi-source runner

The runner independently rejects duplicate source IDs and duplicate normalized MQTT topic
identities before opening the shared publisher, any source, or any task. This preserves the
invariant even when callers construct the public runner directly rather than through
`SimulatorConfiguration`. It then starts one shared M1 publisher, opens each source, and starts each
source once. Static and periodic sources may coexist. An error from any source is propagated;
cleanup requests stop for all other sources and then closes the publisher. A normal operator
interrupt follows the same cleanup order.

The development profile proves three independent sources—temperature, humidity, and NH3—with
distinct IDs, seeds, and state.

## Publication and M1 integration

The simulator constructs `ObservationEnvelopeV1` and `TopicRoute` instances and calls only
`MqttTelemetryPublisher.publish()`. QoS, PUBACK waits, retry delay, reconnect handling, exact-byte
retry identity, and broker connection state remain M1 responsibilities.

Operators must start the API/ingestion path and wait for `/health/ready` before starting the
simulator. Per ADR-0005, broker PUBACK before the first successful consumer SUBACK is outside the
broker-to-database delivery guarantee. M2 does not claim a durable producer outbox.

## Failure behavior

- Invalid configuration fails before any MQTT connection or source task is started.
- Invalid MQTT duration overrides fail with a nonzero structured CLI error before publisher
  construction or network activity.
- Duplicate runner source or normalized routing identities fail before publisher/source startup.
- MQTT unavailability at startup and PUBACK retry exhaustion surface M1 `BrokerUnavailable`.
- MQTT disconnection during publication uses M1's bounded reconnect/retry behavior.
- A deterministic generation error fails the source once and is never retried forever.
- A stop during cadence returns promptly; a stop during publication waits for the bounded M1
  publication attempt.
- Runner cleanup stops sibling sources and closes the publisher.
- No failed publication is logged or reported as successful.

M2 inherits, and does not strengthen, the delivery limitations accepted in ADR-0005.

## Observability

Simulator logs use the existing JSON logging setup. INFO events cover runner/source start and stop.
Failures include safe source ID and measurement context. Successful generation is DEBUG-only; raw
telemetry, credentials, and connection strings are not logged. M1 retains its own publisher and
ingestion events.

## Operator and development usage

From a synchronized workspace:

```bash
docker compose up -d --wait postgres mqtt api
curl --fail http://127.0.0.1:8000/health/ready
uv run pigwatch-simulator --config configs/simulator.development.json
```

The process runs until interrupted when periodic sources are configured. A static configuration
publishes once per source and exits. MQTT host, port, timeouts, attempts, and publisher client ID
are non-secret environment settings. No LLM key or paid service is required.

No simulator container is introduced in M2: the lightweight package entry point is sufficient for
development, avoids another operated service, and keeps the modular-monolith boundary from
ADR-0001.

## Security assumptions

M2 preserves M1 local-development assumptions. MQTT and PostgreSQL remain loopback-bound in
Compose, anonymous MQTT is not exposed publicly, and no credentials are committed. Configuration
contains routing and generation values only. Production authentication, TLS, authorization,
deployment, retention, and durable edge buffering remain future decisions.

## Testing strategy

Unit and contract tests cover:

- valid and invalid configuration, including cadence and finite numeric rules;
- fixed-seed reproducibility and different-seed divergence;
- inclusive bounds, extreme finite-domain step safety, and exact supported payload/unit mapping;
- deterministic UTC clocks and rejection of naive time;
- `SYNTHETIC` + `LIVE` provenance and null replay/ingest times;
- unique event IDs for genuine observations and exact identity/bytes across M1 retries;
- static and periodic behavior, lifecycle transitions, duplicate-start prevention, stop during wait,
  stop during publication, failures, and task cleanup;
- direct runner identity validation before resource acquisition and concurrent valid composition;
  and
- finite positive MQTT duration validation, including structured CLI rejection without network
  activity.

Integration tests use real Mosquitto and PostgreSQL and cover all three measurements through the
M1 path, concurrent sources, source/routing identity, event and ingest times, deterministic
sequences, idempotent duplicate delivery, broker interruption/recovery, and clean simulator stop.
The complete M1 suite remains regression protection.

## Acceptance criteria

M2 is acceptable when:

1. all three environmental measurements generate M1-compatible envelopes and units;
2. fixed configuration, seed, and clock reproduce the same sequence;
3. every runtime observation is `SYNTHETIC` + `LIVE` with null `replay_time` and producer-null
   `ingest_time`;
4. every normal publication uses the M1 publisher and real MQTT ingestion path;
5. event identity is unique between genuine readings and stable across publication retry;
6. static mode emits once and periodic mode follows fixed-delay cadence;
7. lifecycle transitions, failure propagation, graceful stop, and task cleanup are explicit;
8. the public runner rejects duplicate source/routing identities before resource acquisition, and
   three independent configured sources may run concurrently;
9. real MQTT/PostgreSQL round trips preserve source, payload, unit, and event time while assigning
   ingest time;
10. temporary broker interruption recovers within M1 semantics without duplicate durable rows;
11. all M1 regression, Python, frontend, Docker/Compose, audit, link, secret, and scope checks pass;
12. documentation and limitations match implementation; and
13. no M3 or later behavior is implemented.

## Known limitations

- The signals are synthetic bounded random walks, not scientifically calibrated farm models.
- Only temperature, relative humidity, and NH3 scalar observations are supported.
- There is no animal physiology, health, disease, anomaly, or ground-truth behavior.
- Recorded simulator replay is not implemented; existing M1 recorded-contract fixtures remain
  unchanged.
- Sensor drift, correlated environments, sensor faults, missing samples, and realistic control
  dynamics are not modeled.
- Simulator state is in memory and intentionally has no persistence or durable outbox.
- M1's pre-SUBACK loss boundary and other accepted delivery limits remain.
- The entry point is for local development, not a production deployment design.
