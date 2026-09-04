# PigWatch

PigWatch is a simulation-first livestock health monitoring platform. It is designed to detect and communicate physiological and behavioral anomalies; it is not an autonomous veterinary diagnostic system.

This repository contains the **M1 telemetry core** on top of the closed M0 foundation. Typed
observations can travel through MQTT ingestion into PostgreSQL and be retrieved through the API.
Sensor simulation, computer vision, anomaly detection, alerts, analytics and hardware integrations
belong to later milestones.

## Repository layout

```text
apps/dashboard/          React + TypeScript operator dashboard shell
services/api/            FastAPI service and health endpoints
packages/python/         Shared schemas, source contracts, telemetry, and future package seams
infra/                   Local infrastructure configuration
tests/                   Cross-package Python tests
docs/                    Product, architecture, ADR, specification, and plan records
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for system boundaries and [AGENTS.md](AGENTS.md) for repository working rules.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 22.23.2 (see `.nvmrc`)
- npm 12.0.2 (pinned by `packageManager` and verified in CI/Docker)
- Docker with Docker Compose (optional for local infrastructure)

## First-time setup

Select the pinned Node version and install the pinned npm version before installing dependencies. With `nvm`:

```bash
nvm use
npm install --global npm@12.0.2
```

Then install from the repository lockfiles:

```bash
uv sync --all-packages --dev --locked
npm ci
```

Compose has non-secret, loopback-only defaults so configuration, image builds, and isolated smoke tests work from a clean checkout. For regular or shared development, copy `.env.example` to `.env` and replace every placeholder before starting Docker services. `.env` is ignored by Git.

## Development commands

Run the API:

```bash
uv run alembic -c services/api/alembic.ini upgrade head
uv run --package pigwatch-api uvicorn pigwatch_api.main:app --reload
```

Run the dashboard:

```bash
npm run dev --workspace @pigwatch/dashboard
```

Run validation:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy services packages tests
uv run pytest
npm run check
```

Run the local stack after configuring `.env`; the API container applies migrations before startup:

```bash
docker compose up --build
```

The dashboard is served at `http://localhost:5173`. API liveness is at
`http://localhost:8000/health/live`; readiness at `/health/ready` returns HTTP 200 only when
PostgreSQL is available, the MQTT consumer's intended QoS 1 subscription has received a successful
SUBACK, and bounded ingestion capacity is available. Producers must wait for readiness before
assuming the broker-to-database path exists. Minimal retrieval endpoints are:

```text
GET /v1/observations/{event_id}
GET /v1/observations?source_id=...&payload_type=...&event_time_from=...&event_time_to=...
```

The MQTT observation topic is
`pigwatch/v1/observations/{scope_kind}/{scope_id}/{source_id}/{category}` with QoS 1. The consumer
ACKs only after a durable acceptance or rejection transaction. See
[`docs/specs/m1-telemetry-core.md`](docs/specs/m1-telemetry-core.md) for the exact contract and actual
delivery guarantee, including the explicit pre-subscription loss boundary.

The initial Digital Farm is planned for M4 as a browser feature built with React, TypeScript,
Three.js, and React Three Fiber. No 3D engine dependency or rendering behavior is included in M1.

## Product guardrail

PigWatch outputs must be framed as observations, anomaly indications, and decision support. They must not claim that the system independently diagnoses disease or replaces a veterinarian.

## Roadmap

M0 established tooling and boundaries. M1 implements the telemetry core. The current milestone
sequence lives in [docs/product/roadmap.md](docs/product/roadmap.md); M2 sensor simulation has not
started.
