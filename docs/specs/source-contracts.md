# Source Contract Foundation

## Status

M0 foundation. Capability payloads are intentionally deferred.

## Common lifecycle contract

A PigWatch source lifecycle:

- exposes one stable, immutable descriptor with explicit origin and delivery provenance;
- opens resources asynchronously; and
- closes resources asynchronously and idempotently.

The M0 Python protocol is `pigwatch_sources.SourceLifecycle`. It is a static structural contract, so implementations do not inherit framework code and no runtime protocol checking is provided.

M0 intentionally defines no `read()` method or universal acquisition mechanism. Cameras, RFID, thermal arrays, environmental sensors, simulation, and recorded replays may need different streaming, batching, EOF, subscription, backpressure, and cancellation semantics. Their owning milestones must specify those semantics instead of inheriting a premature common pull model.

## Capability contracts

The milestone that first uses a capability defines its sample schema and acquisition contract while reusing the common lifecycle where appropriate:

- camera: M5;
- RFID: M8;
- thermal: M9;
- environmental sensors: M2 for synthetic semantics, refined with real adapters in M17.

Implementations with expected names include `VideoFileSource`, `WebcamSource`, `RTSPSource`, synthetic adapters, and physical hardware adapters. Names do not replace explicit `SourceOrigin` and `SourceDelivery` values.

## Required contract-test themes

- descriptor identity, source origin, and source delivery remain stable;
- open behavior is explicit and independently testable;
- close is idempotent where the shared contract promises it;
- static typing accepts conforming implementations without runtime attribute checks;
- timestamps, units, and quality metadata conform to the capability schema;
- simulation seeds produce repeatable sequences when promised;
- recorded delivery preserves capture time separately from replay/ingest time and never rewrites source origin;
- failures do not fabricate valid-looking observations.
