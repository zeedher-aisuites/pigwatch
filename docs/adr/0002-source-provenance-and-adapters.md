# ADR-0002: Source provenance and adapter boundaries

- Status: Proposed
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

PigWatch must support synthetic inputs and physical hardware delivered either live or from recordings without creating separate downstream products or allowing synthetic evidence to be mistaken for physical evidence.

## Decision

Every source descriptor declares two orthogonal provenance dimensions:

- `SourceOrigin` is `SYNTHETIC` or `PHYSICAL` and records where evidence ultimately originated.
- `SourceDelivery` is `LIVE` or `RECORDED` and records whether evidence is delivered as produced or replayed from storage.

Origin survives recording, transformation, storage, replay, and re-ingestion. A synthetic recording therefore remains `SYNTHETIC` + `RECORDED`; a physical recording is `PHYSICAL` + `RECORDED`.

Downstream components depend on capability-specific source interfaces rather than concrete device or simulation implementations. M0 defines only a static `SourceLifecycle` protocol containing descriptor access, asynchronous `open()`, and idempotent `close()`. It deliberately defines no universal acquisition method; capability milestones own streaming, batching, EOF, subscription, backpressure, cancellation, and payload semantics.

Simulation ground truth, PigWatch observations, and PigWatch inferred state use separate contracts and storage semantics. They may be correlated for evaluation but are never implicitly substituted.

## Consequences

Source implementations are replaceable and contract-testable without forcing incompatible capabilities into one pull model. Both provenance dimensions must be carried through telemetry and persistence. Some duplication across capability-specific acquisition interfaces is accepted in exchange for clearer semantics.

## Alternatives considered

- Separate simulation pipeline: rejected because it would allow production and test behavior to diverge.
- One `SIMULATED`/`RECORDED`/`LIVE` enum: rejected because it conflates evidence origin with delivery and loses synthetic origin during replay.
- One untyped universal sensor interface: rejected because frames, RFID reads, thermal arrays, and environment samples have different lifecycle and validation needs.
- A universal `read()` method in M0: rejected because it prematurely fixes pull, item, EOF, and backpressure semantics.
- Infer provenance from adapter names or topic paths: rejected because provenance would be lost after transformation.

## Follow-up

M1 must carry source origin and delivery independently in the telemetry envelope. M2 and later sensor milestones must add capability acquisition/payload contracts and shared contract tests.
