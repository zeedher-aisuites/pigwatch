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
| Source contracts | Interfaces shared by simulated, recorded, and live adapters | `packages/python/pigwatch-sources` |
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

The M0 `AsyncSource` protocol captures only common lifecycle and provenance. Capability milestones own typed payloads and contract tests. Adapters translate vendor formats, expose acquisition timestamps and source health, and manage device lifecycle; they do not perform anomaly detection or diagnosis. Replacing simulation with hardware should replace an adapter, not force a backend rewrite.

Seeded synthetic scenarios should eventually be deterministic. The same contract-test suite should be reusable across simulated, recorded, and live implementations, and failures or missing samples must be explicit rather than replaced by plausible synthetic values.

## Source modes and provenance

Every input declares one source mode:

- `SIMULATED`: generated by a controlled scenario; any ground truth remains on a separate evaluation path.
- `RECORDED`: replayed from captured media or telemetry; capture, replay, and ingest times remain distinguishable.
- `LIVE`: acquired from a device or external system in operational time.

Mode is provenance, not a quality ranking. It travels with an observation through persistence and derived evidence and remains filterable in APIs and user interfaces. Synthetic or replayed data must never masquerade as live data.

## Telemetry and event-driven concepts

M1 will define the telemetry envelope and MQTT topic taxonomy. MQTT is the preferred decoupled, near-real-time transport; Pydantic validates versioned boundary data; PostgreSQL stores normalized observations and derived metadata. Events will carry an event identifier, schema version, source and optional animal identifiers, event and ingest times, source mode, units, and quality metadata.

Delivery is assumed to be at least once. Consumers must be idempotent and tolerate late, duplicated, and out-of-order events. The exact QoS, topic, retention, retry, dead-letter, and schema-evolution rules remain M1 decisions.

## Persistence concepts

PostgreSQL is the primary transactional and historical store, with schemas and indexing designed to remain compatible with time-series workloads. Raw observations, normalized records, inferred state, model versions, provenance, and processing outcomes remain traceable. High-volume media should live in appropriate object/file storage and be referenced by metadata rather than stored as large relational blobs. Retention, partitioning, time-series extensions, backup, and disaster recovery are deliberately undecided in M0.

## Deterministic analytics and LLM boundary

Deterministic validation, normalization, rules, statistical methods, and purpose-trained models produce anomaly/risk evidence. **LLMs must NOT directly decide whether an animal is sick.** An optional LLM may explain already-structured evidence, retrieve contextual veterinary material, or adapt delivery language, but it is not the source of truth for physiological anomaly detection. LLM output must retain links to evidence, uncertainty, and model provenance and must not silently upgrade an anomaly into a diagnosis.

## Browser-based Digital Farm

The initial Digital Farm will be part of the browser experience using React, TypeScript, Three.js, and React Three Fiber. This keeps simulation visualization close to the dashboard and avoids a second engine and deployment toolchain. It still consumes stable APIs/contracts rather than becoming the simulator's source of truth. Godot and Unreal Engine are possible future tools only if measured browser limitations justify them; neither is a current dependency or roadmap milestone.

## Future hardware integration

Live device integrations implement the same capability contracts as simulated and recorded sources. Vendor SDKs and physical protocols remain in edge adapters, which translate into canonical observations with explicit `LIVE` provenance. Device discovery, credentials, buffering, clock synchronization, intermittent connectivity, and edge deployment require dedicated ADRs/specifications when real hardware work begins.

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
