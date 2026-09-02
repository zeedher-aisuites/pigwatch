# Repository Layout

PigWatch uses a monorepo so contracts, adapters, services, the dashboard, simulation code, tests, and local infrastructure configuration can evolve atomically.

- `apps/` contains user-facing applications.
- `services/` contains independently runnable backend processes.
- `packages/` contains reusable code and stable seams; packages must not import applications or services.
- `infra/` contains local infrastructure configuration, not production secrets.
- `tests/` contains cross-package and contract tests; component-local tests may live with components.
- `docs/` contains durable decisions and plans.

Dependency direction is from apps, services, and adapters toward shared schemas and interfaces. Shared packages do not depend on application code.
