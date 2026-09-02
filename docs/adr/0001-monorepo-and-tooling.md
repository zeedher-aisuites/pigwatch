# ADR-0001: Monorepo and baseline tooling

- Status: Accepted
- Date: 2026-09-02
- Owners: PigWatch maintainers

## Context

PigWatch will evolve several tightly related services, shared contracts, simulators, and a dashboard. Early changes need atomic review while the team avoids unnecessary operational complexity.

## Decision

Use one repository with explicit `apps`, `services`, `packages`, `simulators`, `infra`, `tests`, and `docs` boundaries. Use Python 3.12+, uv workspaces, FastAPI/Pydantic, Ruff, mypy, and pytest for Python. Use an npm workspace with React, TypeScript, Vite, and Vitest for the dashboard. Use Docker Compose for local PostgreSQL and MQTT dependencies. GitHub Actions runs deterministic checks from lockfiles.

OpenCV, PyTorch, and Godot are deferred until the milestone that exercises them.

## Consequences

Contracts and consumers can change together, and the development path is straightforward. CI covers multiple ecosystems, and component ownership will need continued discipline as the repository grows. Independent release/version policies may be introduced later without moving repositories.

## Alternatives considered

- Multiple repositories: rejected for now because contract changes would require coordination without providing useful isolation at M0 scale.
- One undifferentiated application package: rejected because it would blur hardware, domain, and presentation boundaries.
- Adding all roadmap dependencies immediately: rejected because unused large dependencies increase installation time and maintenance risk.

## Follow-up

Revisit deployment units and ownership after concrete scaling or team-boundary evidence appears.
