# ADR-0002: Source provenance and adapter boundaries

- Status: Accepted
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

PigWatch must support synthetic inputs, recorded replays, and live hardware without creating separate downstream products or allowing test data to be mistaken for operational evidence.

## Decision

Every source declares `SIMULATED`, `RECORDED`, or `LIVE` provenance. Downstream components depend on capability-specific source interfaces rather than concrete device or simulation implementations. M0 defines only a small asynchronous lifecycle protocol and provenance vocabulary; payload contracts arrive with their owning milestones.

Simulation ground truth and sensor-observed state use separate contracts and channels. They may be correlated for evaluation but are never implicitly substituted.

## Consequences

Source implementations are replaceable and contract-testable. Provenance must be carried through telemetry and persistence. Some duplication across capability-specific interfaces is accepted in exchange for clearer semantics.

## Alternatives considered

- Separate simulation pipeline: rejected because it would allow production and test behavior to diverge.
- One untyped universal sensor interface: rejected because frames, RFID reads, thermal arrays, and environment samples have different lifecycle and validation needs.
- Infer mode from adapter names or topic paths: rejected because provenance would be lost after transformation.

## Follow-up

M1 must include source mode in the telemetry envelope. M2 and later sensor milestones must add capability payloads and shared contract tests.
