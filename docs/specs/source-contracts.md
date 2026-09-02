# Source Contract Foundation

## Status

M0 foundation. Capability payloads are intentionally deferred.

## Common contract

An asynchronous PigWatch source:

- exposes immutable source identity and one explicit source mode;
- opens before reads and closes idempotently;
- returns typed samples through `read()`;
- raises implementation-specific failures that an owning adapter boundary translates into future source-health events.

The M0 Python protocol is `pigwatch_sources.AsyncSource`. It is a structural contract, so implementations do not inherit framework code.

## Capability contracts

The milestone that first uses a capability defines its sample schema and extends the common lifecycle as needed:

- camera: M5;
- RFID: M8;
- thermal: M9;
- environmental sensors: M2 for synthetic semantics, refined with real adapters in M17.

Implementations with expected names include `VideoFileSource`, `WebcamSource`, `RTSPSource`, and synthetic/live hardware adapters. Names do not replace explicit provenance.

## Required contract-test themes

- declared identity and source mode remain stable;
- lifecycle calls are safe and documented;
- timestamps, units, and quality metadata conform to the capability schema;
- simulation seeds produce repeatable sequences when promised;
- recorded replay preserves capture time separately from replay/ingest time;
- failures do not fabricate valid-looking observations.
