# ADR-0004: Browser-based Digital Farm

- Status: Proposed
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

PigWatch needs an interactive farm view that can later present simulation and monitoring state. Introducing a game engine in the early roadmap would add a separate language, build pipeline, deployment target, and integration boundary before browser limitations are known.

## Decision

Build the initial Digital Farm in M4 as part of the web application using React, TypeScript, Three.js, and React Three Fiber. Keep simulation truth and sensor behavior outside the rendering layer and expose them through stable contracts. Do not add the 3D dependencies or rendering implementation during M0.

Godot and Unreal Engine remain possible future options only if measured browser performance, fidelity, device access, or workflow constraints make the browser approach insufficient.

## Consequences

The dashboard and Digital Farm share a delivery surface and frontend skill set. The rendering layer stays replaceable because it consumes contracts rather than owning simulation state. Very high-fidelity or large-scale scenes may eventually require reevaluation.

## Alternatives considered

- Godot first: deferred because its additional runtime and integration boundary are not justified for the initial farm view.
- Unreal Engine first: deferred because its footprint and operational complexity exceed current needs.
- Static 2D visualization: insufficient as the roadmap calls for an interactive spatial farm, though 2D views may complement it.

## Follow-up

M4 must define performance budgets, browser support, scene/state ownership, accessibility, and the API contract before adding 3D dependencies.
