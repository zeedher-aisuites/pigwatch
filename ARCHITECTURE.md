# PigWatch Architecture

## Purpose and guardrails

PigWatch collects livestock observations, detects physiological, environmental, and behavioral anomalies, and presents decision support to farm operators and veterinary professionals. It does not independently diagnose disease or prescribe treatment. Clinical language must preserve uncertainty, show supporting evidence, and direct users to qualified veterinary judgment.

M0 established boundaries and development tooling. M1 adds typed observation transport,
validation, MQTT ingestion, PostgreSQL persistence and minimal retrieval. M2 adds deterministic
synthetic environmental sources that use that accepted path. M3 adds a read-only operator dashboard
over the M1 API with system status, bounded telemetry presentation, factual freshness, filtering,
detail, and discrete historical visualization. M4 adds a browser-rendered deterministic development
farm whose local placement configuration joins to that same telemetry by exact source ID. These
milestones intentionally contain no animal behavior or physiology, simulation ground truth
ingestion, vision pipeline, anomaly engine, alerting, prediction or veterinary retrieval behavior.

## System boundary and architecture style

Inside PigWatch are capability adapters, ingestion and validation, normalization, persistence, sensor fusion, deterministic analytics, APIs, operator experiences, simulation evaluation, and notification coordination. Outside PigWatch are physical devices before an adapter, vendor protocols and SDKs, third-party messaging/speech/model/knowledge services, farm systems of record, veterinary diagnosis and treatment, and operational decisions.

Integrations cross the boundary through explicit adapters. Domain code must not depend directly on device SDKs, transport clients, UI frameworks, or third-party response formats.

PigWatch begins as a modular monolith in a monorepo. Clear package and service seams support independent testing and possible later extraction, but a component becomes a separately operated service only when scaling, reliability, deployment, or ownership evidence requires it.

## Major components

| Component | Responsibility | Location |
| --- | --- | --- |
| Dashboard | React/TypeScript read-only telemetry view and M4 browser Digital Farm | `apps/dashboard` |
| API | FastAPI health/retrieval boundary and in-process telemetry worker | `services/api` |
| Shared schemas | Versioned, transport-neutral vocabulary and provenance | `packages/python/pigwatch-schemas` |
| Source contracts | Lifecycle shared by source adapters without universal acquisition semantics | `packages/python/pigwatch-sources` |
| Simulation | M2 deterministic synthetic environmental sources and concurrent local runner; future scenario/evaluation seam | `packages/python/pigwatch-simulation` |
| Vision | Future camera ingestion and computer-vision boundary | `packages/python/pigwatch-vision` |
| Telemetry | MQTT publishing/ingestion, validation, normalization and PostgreSQL persistence | `packages/python/pigwatch-telemetry` |
| Local infrastructure | PostgreSQL, MQTT, and containerized development configuration | `compose.yaml`, `infra` |

## Preferred data flow

```text
raw observations
  -> validation
  -> normalization
  -> persistence
  -> sensor fusion
  -> anomaly/risk models
  -> structured evidence
  -> optional LLM explanation
  -> notification/UI
```

Capability adapters add identity and provenance at acquisition. MQTT may transport observation events to ingestion, but transport details do not alter domain contracts. Control messages, configuration, acknowledgements, and operational logs/metrics/traces use separate contracts and must not be disguised as livestock observations.

## Ground truth, observations, and inferred state

1. **Simulation ground truth** is the simulator's authoritative internal scenario state, such as animal positions, assigned identities, generated physiology, environmental conditions, and injected events.
2. **PigWatch observations** are noisy or incomplete sensor and algorithm readings, including occlusion, sampling gaps, confidence, and delay. Production hardware normally supplies observations only.
3. **PigWatch inferred state** is the system's estimate produced from observations, history, fusion, and deterministic or validated statistical models. It is neither raw evidence nor simulation truth.

These states use separate contracts and storage semantics. Evaluation may correlate them through explicit scenario and correlation identifiers, but simulation ground truth must never enter normal inference as sensor evidence. APIs and user interfaces must label which state is shown.

## Simulation-first and adapter philosophy

Simulation is a first-class, reproducible input mode, not a demo-only path. Each capability is designed against a stable interface before hardware specifics are introduced. Future ports include `CameraSource`, `ThermalSource`, `RFIDSource`, and `EnvironmentSource`; adapters may include `SimulationCameraSource`, `VideoFileSource`, `WebcamSource`, `RTSPSource`, synthetic sensor sources, and vendor hardware implementations.

The M0 `SourceLifecycle` protocol captures only immutable descriptor access plus asynchronous `open()` and idempotent `close()`. It deliberately defines no universal read, iterator, callback, stream, batch, EOF, subscription, backpressure, or cancellation model. Capability milestones choose acquisition semantics only after their requirements are known and own their typed payloads and contract tests.

Adapters translate vendor formats, expose acquisition timestamps and source health, and manage device lifecycle; they do not perform anomaly detection or diagnosis. Replacing simulation with hardware should replace an adapter, not force a backend rewrite.

Seeded synthetic scenarios should eventually be deterministic. Lifecycle and provenance contract tests should be reusable across source implementations, while capability-specific suites validate their chosen acquisition models. Failures or missing samples must be explicit rather than replaced by plausible synthetic values.

## M2 environmental sensor simulation

M2 defines the first capability-specific acquisition behavior without expanding the generic source
lifecycle. Each `EnvironmentalSensorSimulator` has immutable identity, local seeded value and event
random streams, an injectable UTC clock, and explicit lifecycle state. It produces one of the three
existing M1 scalar payloads using a bounded random walk. The first value is configured; subsequent
values add a seeded uniform step and clamp to configured bounds.

Static mode publishes one observation. Periodic mode publishes immediately and then uses a
fixed-delay cadence after each successful publication, so missed time does not create a catch-up
burst. One task owns each source loop, while a small runner may compose multiple independent sources
through one M1 MQTT publisher. Stop interrupts cadence waits and lets an in-flight bounded M1
publication settle before cleanup.

Generated M2 evidence is always `SYNTHETIC` + `LIVE`. The event time and deterministic UUIDv7 are
created before publication; the immutable envelope is reused by M1 for PUBACK retries. The simulator
does not add a retry layer, durable outbox, database state, direct ingestion call, recorded replay,
or simulation ground-truth contract. Exact behavior is specified in
[`docs/specs/m2-sensor-simulator.md`](docs/specs/m2-sensor-simulator.md).

## M3 basic dashboard

M3 consumes only the M1 HTTP boundary. Its typed TypeScript client validates liveness, readiness,
and observation responses before they enter React state. The dashboard server proxies a relative
`/api` path to the API in both Vite development and the Nginx Compose image, so the browser never
connects to PostgreSQL or MQTT and no permissive cross-origin API policy is required.

The existing observation query retains its ascending default and adds optional `order=desc` so a
bounded caller can retrieve the newest evidence truthfully. M3 requests 200 observations by default,
within M1's 500-row maximum. Source, measurement, and time filtering operate over that bounded
client result; no analytics or aggregate endpoint is introduced.

One local hook owns liveness, readiness, observations, errors, retained last-known data, and
completion-scheduled polling. Requests do not overlap. Timers and active requests are cleaned on
unmount, and scheduled requests pause while the document is hidden. A 60-second default freshness
policy compares the newest loaded event time with the browser clock and is explicitly presentation
policy rather than biological meaning.

Presentation keeps `SYNTHETIC`/`PHYSICAL` origin separate from `LIVE`/`RECORDED` delivery in latest
readings, the observation list, and detail. A dependency-free SVG uses discrete actual points for a
single source/measurement/unit series; exact values remain in the table. No inferred state,
threshold, anomaly, health, spatial, 3D, or M4 behavior exists. Exact behavior is specified in
[`docs/specs/m3-basic-dashboard.md`](docs/specs/m3-basic-dashboard.md).

## M4 Interactive Digital Farm

M4 extends the existing browser shell with a Digital Farm view while retaining the complete M3
telemetry console. One M3 `useTelemetry` hook remains the data owner. A bounded frontend derivation
joins the latest matching observation to each configured marker by exact `source_id`; the 3D scene
does not fetch, subscribe to MQTT, query PostgreSQL, or mutate observation evidence.

The deterministic development layout lives only under `apps/dashboard/src/digital-farm`. It maps
the three existing M2 source identities to descriptive Pen A, Pen B, and Service Aisle placements in
meters. This compile-time configuration is presentation metadata—not an API, persisted model,
shared schema, survey, or future compatibility promise—so M4 adds no durable spatial contract and
requires no new ADR. A future cross-service or persistent facility model requires Product Owner
review and a dedicated ADR.

Three.js and React Three Fiber render procedural farm geometry in a lazy browser chunk with a
demand-based frame loop and constrained OrbitControls. The semantic sensor directory and factual
selection detail remain outside WebGL and usable through the keyboard. WebGL unsupported, context
loss, lazy loading, render failure, missing telemetry, and unplaced telemetry are explicit. Exact
behavior, camera, performance, accessibility, and lifecycle requirements are specified in
[`docs/specs/m4-interactive-digital-farm.md`](docs/specs/m4-interactive-digital-farm.md).

## Source provenance

Every source descriptor declares two orthogonal dimensions:

- `SourceOrigin.SYNTHETIC`: evidence ultimately produced by a controlled simulation.
- `SourceOrigin.PHYSICAL`: evidence ultimately acquired from a physical device or external physical system.
- `SourceDelivery.LIVE`: delivered as it is produced or acquired in the current execution.
- `SourceDelivery.RECORDED`: replayed from stored media or telemetry.

These dimensions can combine: a synthetic scenario can be delivered live or replayed later, and a physical capture can be processed live or replayed. Recording, transformation, storage, and re-ingestion may change delivery but must never erase or rewrite origin. Synthetic evidence therefore remains identifiable as synthetic throughout persistence and derived evidence. For recorded delivery, capture, replay, and ingest times remain distinguishable.

## Telemetry and event-driven concepts

M1 defines a strict version `1.0` observation envelope with UUIDv7 identity, independent origin and
delivery provenance, UTC event/replay/ingest times, typed scalar fixture payloads, explicit units,
and optional quality/trace metadata. Recorded delivery requires `replay_time`; live delivery
forbids it. The producer sends `ingest_time: null`; PigWatch assigns the authoritative acceptance
time. Simulation ground truth has no observation payload, topic, table or API.

Observation topics use
`pigwatch/v1/observations/{scope_kind}/{scope_id}/{source_id}/{category}`. MQTT v5 QoS 1,
persistent broker storage and a 24-hour consumer session support redelivery. The consumer manually
ACKs only after PostgreSQL commits an acceptance or rejection. UUID primary-key idempotency
collapses duplicates only when both canonical content and normalized routing topic match; changed
content or routing is an explicit event-ID conflict.

The broker-to-database at-least-once path begins only after the persistent QoS 1 consumer
subscription receives a successful SUBACK and remains subject to configured persistence, session
and storage limits. A fresh broker may PUBACK a publication made before that subscription exists
without retaining it for the later consumer. M1 therefore does not claim unconditional
producer-to-database durability: producers have no durable outbox and must gate operational startup
on API readiness. Exact semantics are normative in
[`docs/specs/m1-telemetry-core.md`](docs/specs/m1-telemetry-core.md) and proposed for approval in
[ADR-0005](docs/adr/0005-telemetry-contract-delivery-and-storage.md).

## Persistence concepts

PostgreSQL is the primary transactional and historical store. Alembic creates an `observations`
table keyed by event ID and a `telemetry_rejections` evidence table. Accepted rows retain exact
bounded MQTT bytes alongside normalized query columns. Indexes support event ID, source/time,
payload/time and ingest-time access. Late and future-skew flags preserve evidence without rewriting
timestamps. Retention, partitioning, time-series extensions, production access control, backup and
disaster recovery remain undecided.

The API process is live independently of dependencies. It is ready only when PostgreSQL answers a
probe, the MQTT worker is connected, its intended subscription has a successful SUBACK, and the
bounded ingestion capacity is not saturated. MQTT Receive Maximum and an application semaphore
bound in-flight deliveries and concurrent PostgreSQL work. Shutdown stops new work and awaits
processing cleanup within a finite deadline before repository disposal. Broker and database loss
are visible in JSON logs and readiness without terminating the process.

## Deterministic analytics and LLM boundary

Deterministic validation, normalization, rules, statistical methods, and purpose-trained models produce anomaly/risk evidence. **LLMs must NOT directly decide whether an animal is sick.** An optional LLM may explain already-structured evidence, retrieve contextual veterinary material, or adapt delivery language, but it is not the source of truth for physiological anomaly detection. LLM output must retain links to evidence, uncertainty, and model provenance and must not silently upgrade an anomaly into a diagnosis.

## Browser-based Digital Farm

The initial Digital Farm is part of the browser experience using React, TypeScript, Three.js, and
React Three Fiber. This keeps simulation visualization close to the dashboard and avoids a second
engine and deployment toolchain. It consumes the accepted M1 API through M3 state rather than
becoming the simulator's source of truth. Godot and Unreal Engine are possible future tools only if
measured browser limitations justify them; neither is a current dependency or roadmap milestone.

## Future hardware integration

Live device integrations implement the same capability contracts as synthetic sources and recorded replays. Vendor SDKs and physical protocols remain in edge adapters, which translate into canonical observations with `PHYSICAL` origin and the appropriate `LIVE` or `RECORDED` delivery. Device discovery, credentials, buffering, clock synchronization, intermittent connectivity, and edge deployment require dedicated ADRs/specifications when real hardware work begins.

## Technology baseline

- Backend: Python 3.12+, FastAPI, and Pydantic.
- Data: PostgreSQL with a time-series-compatible design.
- Telemetry: MQTT.
- Computer vision: OpenCV; PyTorch only when a concrete model requires it.
- Frontend: React, TypeScript, and Vite.
- Digital Farm: Three.js and React Three Fiber in the browser.
- Local orchestration: Docker Compose.
- Testing: pytest and Vitest.
- Quality: Ruff, mypy, the TypeScript compiler, and frontend linting when the source surface warrants it.
- CI: GitHub Actions.

OpenCV, PyTorch, hardware SDKs, and external AI/alert integrations remain absent. Three.js and React
Three Fiber are introduced only for the M4 browser presentation accepted by ADR-0004.

## Cross-cutting constraints and governance

- Secrets enter through runtime configuration and never source control.
- Shared schemas evolve deliberately, compatibly, and with explicit versions.
- UTC is canonical for transport and persistence; presentation may localize time.
- SI units are canonical unless a schema explicitly documents otherwise.
- Raw evidence and derived conclusions remain traceable and observable.
- Significant architecture changes require an ADR under `docs/adr/`; behavior contracts belong in `docs/specs/`.
- Temporary gaps belong in `docs/known-limitations/`; unfinished work is not hidden in `TODO` or `FIXME` comments.
