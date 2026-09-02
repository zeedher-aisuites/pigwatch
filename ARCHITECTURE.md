# PigWatch Architecture

## Purpose and guardrails

PigWatch collects livestock observations, detects physiological or behavioral anomalies, and presents decision support to farm operators and veterinary professionals. It does not independently diagnose disease. Any future clinical interpretation must preserve uncertainty, show supporting observations, and direct users to qualified veterinary judgment.

M0 establishes boundaries and development tooling. It intentionally contains no telemetry pipeline, sensor simulator, vision processing, anomaly engine, or alerting behavior.

## System boundary

Inside the PigWatch platform boundary:

- source adapters for cameras, thermal sensors, RFID readers, environmental sensors, recordings, and simulations;
- ingestion, normalization, telemetry transport, persistence, feature extraction, fusion, anomaly analysis, and historical analysis;
- APIs and operator experiences, including future web, Telegram, and generated-voice delivery;
- simulation orchestration and validation tooling.

Outside the boundary:

- physical devices and vendor protocols before they enter a PigWatch adapter;
- third-party messaging, speech, model, and veterinary-knowledge services;
- farm operational decisions, veterinary diagnosis, and treatment;
- identity registries or systems of record owned by a farm.

Integrations cross the boundary through explicit adapters. Domain services must not depend directly on device SDKs, transport clients, UI frameworks, or third-party response formats.

## Major components

| Component | Responsibility | M0 location |
| --- | --- | --- |
| Dashboard | Operator-facing presentation and future control plane | `apps/dashboard` |
| API | HTTP boundary, health checks, and future query/command endpoints | `services/api` |
| Shared schemas | Versioned, transport-neutral data vocabulary and provenance | `packages/python/pigwatch-schemas` |
| Source contracts | Stable interfaces implemented by simulated, recorded, and live adapters | `packages/python/pigwatch-sources` |
| Simulation | Synthetic-source implementations and scenarios beginning in M2 | `packages/python/pigwatch-simulation` |
| Vision | Camera ingestion and vision pipeline boundary beginning in M4 | `packages/python/pigwatch-vision` |
| Godot simulation | Future visual/digital-farm simulator boundary | `simulators/godot` |
| Telemetry | Future ingestion, MQTT topics, normalization, and persistence beginning in M1 | architecture boundary only in M0 |
| Local infrastructure | PostgreSQL, MQTT, and containerized development services | `compose.yaml`, `infra` |

## Data flow

The intended one-way observation path is:

```text
physical device / recording / scenario
             |
      capability adapter
             |
  observation + provenance
             |
  MQTT ingestion and validation
             |
 normalized telemetry + PostgreSQL history
             |
 feature extraction / fusion / anomaly analysis
             |
     API and alert policies
             |
 dashboard / Telegram / voice / external consumers
```

Control messages, configuration, and acknowledgements use separate contracts and authorization paths; they are not disguised as observations.

## Simulation-first philosophy

Simulation is a first-class source of reproducible observations, not a demo-only code path. A capability is designed against a source contract before a hardware adapter is introduced. Downstream code consumes canonical observations and provenance, so replacing a synthetic adapter with recorded media or live hardware does not change downstream business logic.

Scenarios should be deterministic when seeded, able to run faster than wall clock when practical, and emit ground truth separately from what virtual sensors observe. The same contract tests should be reusable across simulated and live implementations.

## Adapter and interface philosophy

PigWatch uses capability-specific ports such as `CameraSource`, `ThermalSource`, `RFIDSource`, and `EnvironmentSource`. Concrete adapters may include `SimulationSource`, `VideoFileSource`, `WebcamSource`, `RTSPSource`, synthetic sensor adapters, and future vendor hardware adapters.

The M0 `AsyncSource` protocol captures lifecycle and provenance common to all sources without prematurely defining sensor payloads. Milestones that introduce a capability must add its typed interface and contract tests. Adapters own vendor/format translation, retry behavior, timestamps available at acquisition, and source health. They must not contain anomaly or diagnosis logic.

Dependencies point inward: adapters depend on contracts; orchestration depends on interfaces; domain analysis does not import concrete adapters.

## Telemetry architecture

M1 will define the telemetry envelope and topic taxonomy. The planned roles are:

- MQTT provides decoupled, near-real-time transport between source adapters and ingestion consumers.
- Pydantic schemas validate boundary data and produce versioned JSON-compatible payloads.
- PostgreSQL stores normalized observations, provenance, source metadata, and processing outcomes; high-volume media remains referenced object data rather than database blobs.
- Event identity, schema version, animal/source identifiers, event time, ingest time, source mode, units, and quality metadata travel with observations.
- Delivery is assumed to be at least once. Consumers must be idempotent and tolerate late or out-of-order events.
- Metrics, structured logs, and traces are operational telemetry and remain distinct from livestock observation telemetry.

The exact envelope, MQTT QoS/topic rules, retention, and migration strategy are M1 decisions and are deliberately not implemented in M0.

## Ground truth and observed state

`GroundTruth` describes the authoritative state of a simulation scenario: animal positions, assigned identities, generated physiological state, environmental conditions, and injected events. It is available to test harnesses and evaluation pipelines.

`ObservedState` is what a sensor or algorithm reports, including noise, occlusion, sampling gaps, confidence, and processing delay. Production hardware normally provides observations only.

Ground truth must never enter normal production inference as if it were sensor evidence. Simulation evaluation may join the two through explicit scenario and correlation identifiers. Storage, APIs, and visual presentation must label which state is being shown.

## Source modes

Every input declares one of these provenance modes:

- `SIMULATED`: generated from a controlled scenario. Ground truth may exist on a separate evaluation channel.
- `RECORDED`: replayed from previously captured media or telemetry. Original capture time and replay time must remain distinguishable.
- `LIVE`: acquired from a device or external system in operational time.

Mode is provenance, not a quality ranking. A recorded or simulated source must not masquerade as live. Source mode travels with observations and should be filterable in persistence and user interfaces.

## Cross-cutting constraints

- Secrets enter through runtime configuration and never source control.
- Schemas evolve compatibly and carry explicit versions.
- UTC is used for transport and persistence; presentation may localize time.
- SI units are canonical unless a schema explicitly documents otherwise.
- Raw evidence and derived conclusions remain traceable.
- Safety-facing text describes anomalies and uncertainty, not diagnoses.

## Architecture governance

Material decisions are recorded under `docs/adr/` using the process in `docs/adr/README.md`. System diagrams and focused explanations belong in `docs/architecture/`; behavior contracts belong in `docs/specs/`. Temporary gaps are explicit in `docs/known-limitations/`.
