# ADR-0001: Monorepo and baseline tooling

- Status: Proposed
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

PigWatch will evolve several tightly related services, shared contracts, simulators, and a dashboard. Early changes need atomic review while the team avoids unnecessary operational complexity.

## Decision

Use one repository with explicit `apps`, `services`, `packages`, `infra`, `tests`, and `docs` boundaries. Keep early runtime code as a modular monolith with separately runnable entry points only where they provide a clear development or operational boundary. Use Python 3.12+, uv workspaces, FastAPI/Pydantic, Ruff, mypy, and pytest for Python. API images install from `uv.lock` with locked semantics.

Use an npm workspace with React, TypeScript, Vite, and Vitest for the dashboard. Pin Node.js 22.23.2 in `.nvmrc`, package metadata, CI, and Docker; pin npm 12.0.2 through `packageManager`, engine metadata, CI, and Docker. This keeps npm lifecycle-script policy consistent across environments. Use Docker Compose for local PostgreSQL and MQTT dependencies. GitHub Actions runs deterministic checks from lockfiles and builds both application images.

OpenCV and PyTorch are deferred until a computer-vision milestone requires them. Three.js and React Three Fiber are deferred to M4. Godot and Unreal Engine are not roadmap dependencies and require a future decision if browser constraints justify reconsideration.

## Consequences

Contracts and consumers can change together, and the development path is straightforward. CI covers multiple ecosystems, and component ownership will need continued discipline as the repository grows. Independent release/version policies may be introduced later without moving repositories.

## Alternatives considered

- Multiple repositories: rejected for now because contract changes would require coordination without providing useful isolation at M0 scale.
- One undifferentiated application package: rejected because it would blur hardware, domain, and presentation boundaries.
- Adding all roadmap dependencies immediately: rejected because unused large dependencies increase installation time and maintenance risk.

## Follow-up

Revisit deployment units and ownership after concrete scaling or team-boundary evidence appears.
