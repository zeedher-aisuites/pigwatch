# Product Principles

## Purpose

PigWatch helps farm operators and veterinary professionals notice physiological and behavioral anomalies earlier by combining observations across sensors and time.

## Safety statement

PigWatch is decision support. It does not independently diagnose veterinary disease, prescribe treatment, or replace professional evaluation. Product language must communicate evidence, confidence, uncertainty, and escalation paths.

## Engineering principles

1. **Simulation-first:** real hardware replaces adapters; it must not require major backend rewrites.
2. **Stable contracts:** shared schemas and interfaces evolve deliberately and compatibly.
3. **Explicit provenance:** every observation preserves independent `SYNTHETIC`/`PHYSICAL` origin and `LIVE`/`RECORDED` delivery; replay never erases synthetic origin.
4. **State separation:** simulation ground truth, PigWatch observations, and PigWatch inferred state are distinct.
5. **Reproducibility:** synthetic scenarios should support deterministic, seeded execution.
6. **Testability:** components and adapters are independently testable against their contracts.
7. **Observability:** failures, invalid data, sensor loss, and processing gaps are explicit.
8. **No silent mocks:** synthetic data is always labeled as synthetic and never substituted for missing live data.
9. **No silent tech debt:** significant unfinished work is tracked explicitly, not hidden in `TODO` or `FIXME` comments.
10. **No premature distribution:** prefer a simple deployable modular monolith before microservices.
11. **No premature AI:** use deterministic logic when it is sufficient; LLMs explain structured evidence and do not decide whether an animal is sick.
12. **Evidence traceability:** raw observations remain traceable through normalization, fusion, risk analysis, and explanation.

Large dependencies and infrastructure are introduced only when a milestone demonstrates the need.
