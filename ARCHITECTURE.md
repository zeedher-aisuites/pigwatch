# PigWatch Architecture

## Purpose and guardrails

PigWatch collects livestock observations, detects physiological, environmental, and behavioral anomalies, and presents decision support to farm operators and veterinary professionals. It does not independently diagnose disease or prescribe treatment. Clinical language must preserve uncertainty, show supporting evidence, and direct users to qualified veterinary judgment.

M0 establishes boundaries and development tooling. It intentionally contains no telemetry processing, sensor behavior, vision pipeline, Digital Farm rendering, anomaly engine, alerting, prediction, or veterinary retrieval behavior.

## System boundary and architecture style

Inside PigWatch are capability adapters, ingestion and validation, normalization, persistence, sensor fusion, deterministic analytics, APIs, operator experiences, simulation evaluation, and notification coordination. Outside PigWatch are physical devices before an adapter, vendor protocols and SDKs, third-party messaging/speech/model/knowledge services, farm systems of record, veterinary diagnosis and treatment, and operational decisions.

Integrations cross the boundary through explicit adapters. Domain code must not depend directly on device SDKs, transport clients, UI frameworks, or third-party response formats.

PigWatch begins as a modular monolith in a monorepo. Clear package and service seams support independent testing and possible later extraction, but a component becomes a separately operated service only when scaling, reliability, deployment, or ownership evidence requires it.

## Major components

| Component | Responsibility | M0 location |
| --- | --- | --- |
| Dashboard | React/TypeScript operator shell; dashboard and browser Digital Farm arrive in M3/M4 | `apps/dashboard` |
| API | FastAPI HTTP boundary and infrastructure health probes | `services/api` |
| Shared schemas | Versioned, transport-neutral vocabulary and provenance | `packages/python/pigwatch-schemas` |
| Source contracts | Lifecycle shared by source adapters without universal acquisition semantics | `packages/python/pigwatch-sources` |
| Simulation | Future deterministic scenarios, synthetic sources, and evaluation support | `packages/python/pigwatch-simulation` |
| Vision | Future camera ingestion and computer-vision boundary | `packages/python/pigwatch-vision` |
| Telemetry | Future MQTT ingestion, normalization, and persistence beginning in M1 | architecture boundary only in M0 |
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

## Source provenance

Every source descriptor declares two orthogonal dimensions:

- `SourceOrigin.SYNTHETIC`: evidence ultimately produced by a controlled simulation.
- `SourceOrigin.PHYSICAL`: evidence ultimately acquired from a physical device or external physical system.
- `SourceDelivery.LIVE`: delivered as it is produced or acquired in the current execution.
- `SourceDelivery.RECORDED`: replayed from stored media or telemetry.

These dimensions can combine: a synthetic scenario can be delivered live or replayed later, and a physical capture can be processed live or replayed. Recording, transformation, storage, and re-ingestion may change delivery but must never erase or rewrite origin. Synthetic evidence therefore remains identifiable as synthetic throughout persistence and derived evidence. For recorded delivery, capture, replay, and ingest times remain distinguishable.

## Telemetry and event-driven concepts

M1 will define the telemetry envelope and MQTT topic taxonomy. MQTT is the preferred decoupled, near-real-time transport; Pydantic validates versioned boundary data; PostgreSQL stores normalized observations and derived metadata. Events are expected to carry an event identifier, schema version, source and optional animal identifiers, event and ingest times, source origin and delivery, units, and quality metadata.

Consumers should be designed to tolerate duplicates and support idempotent handling. End-to-end at-least-once delivery is an M1 design target, not an M0 guarantee. Establishing an actual guarantee requires M1 decisions on stable event identifiers, MQTT QoS, publisher retry or outbox behavior, broker persistence and sessions, consumer acknowledgements, deduplication transaction scope, and the retention window. Topic, dead-letter, ordering, and schema-evolution rules also remain M1 decisions.

## Persistence concepts

PostgreSQL is the primary transactional and historical store, with schemas and indexing designed to remain compatible with time-series workloads. Raw observations, normalized records, inferred state, model versions, provenance, and processing outcomes remain traceable. High-volume media should live in appropriate object/file storage and be referenced by metadata rather than stored as large relational blobs. Retention, partitioning, time-series extensions, backup, and disaster recovery are deliberately undecided in M0.

## Deterministic analytics and LLM boundary

Deterministic validation, normalization, rules, statistical methods, and purpose-trained models produce anomaly/risk evidence. **LLMs must NOT directly decide whether an animal is sick.** An optional LLM may explain already-structured evidence, retrieve contextual veterinary material, or adapt delivery language, but it is not the source of truth for physiological anomaly detection. LLM output must retain links to evidence, uncertainty, and model provenance and must not silently upgrade an anomaly into a diagnosis.

## Browser-based Digital Farm

The initial Digital Farm will be part of the browser experience using React, TypeScript, Three.js, and React Three Fiber. This keeps simulation visualization close to the dashboard and avoids a second engine and deployment toolchain. It still consumes stable APIs/contracts rather than becoming the simulator's source of truth. Godot and Unreal Engine are possible future tools only if measured browser limitations justify them; neither is a current dependency or roadmap milestone.

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

OpenCV, PyTorch, Three.js, React Three Fiber, hardware SDKs, and external AI/alert integrations are intentionally absent from M0 dependencies.

## Cross-cutting constraints and governance

- Secrets enter through runtime configuration and never source control.
- Shared schemas evolve deliberately, compatibly, and with explicit versions.
- UTC is canonical for transport and persistence; presentation may localize time.
- SI units are canonical unless a schema explicitly documents otherwise.
- Raw evidence and derived conclusions remain traceable and observable.
- Significant architecture changes require an ADR under `docs/adr/`; behavior contracts belong in `docs/specs/`.
- Temporary gaps belong in `docs/known-limitations/`; unfinished work is not hidden in `TODO` or `FIXME` comments.
