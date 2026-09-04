# PigWatch

PigWatch is a simulation-first livestock health monitoring platform. It is designed to detect and communicate physiological and behavioral anomalies; it is not an autonomous veterinary diagnostic system.

This repository contains the **M3 basic dashboard** on top of the closed M0 foundation, accepted M1
telemetry core, and closed M2 simulator. Deterministic synthetic temperature, relative-humidity,
and NH3 observations travel through MQTT ingestion into PostgreSQL, are retrieved through the API,
and appear in a read-only operator dashboard with explicit provenance. Computer vision, anomaly
detection, alerts, analytics, animal behavior, and hardware integrations belong to later milestones.

## Repository layout

```text
apps/dashboard/          React + TypeScript read-only telemetry dashboard
services/api/            FastAPI service and health endpoints
packages/python/         Shared schemas, source contracts, telemetry, and future package seams
configs/                 Versioned local simulator configuration
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

The dashboard is served at `http://localhost:5173` and proxies its same-origin `/api` path to the
PigWatch API. API liveness is at
`http://localhost:8000/health/live`; readiness at `/health/ready` returns HTTP 200 only when
PostgreSQL is available, the MQTT consumer's intended QoS 1 subscription has received a successful
SUBACK, and bounded ingestion capacity is available. Producers must wait for readiness before
assuming the broker-to-database path exists. Minimal retrieval endpoints are:

```text
GET /v1/observations/{event_id}
GET /v1/observations?source_id=...&payload_type=...&event_time_from=...&event_time_to=...&order=desc
```

The MQTT observation topic is
`pigwatch/v1/observations/{scope_kind}/{scope_id}/{source_id}/{category}` with QoS 1. The consumer
ACKs only after a durable acceptance or rejection transaction. See
[`docs/specs/m1-telemetry-core.md`](docs/specs/m1-telemetry-core.md) for the exact contract and actual
delivery guarantee, including the explicit pre-subscription loss boundary.

## M2 environmental simulator

The simulator emits simple bounded-random-walk infrastructure signals. They are synthetic test and
demo observations, not scientifically calibrated farm models or veterinary thresholds. Runtime
readings always carry `origin=SYNTHETIC`, `delivery=LIVE`, and a null `replay_time`.

Start the ingestion dependencies and wait for the M1 SUBACK-gated readiness boundary before
starting a periodic simulator:

```bash
docker compose up -d --wait postgres mqtt api
curl --fail http://127.0.0.1:8000/health/ready
uv run pigwatch-simulator --config configs/simulator.development.json
```

The development configuration contains independent temperature, humidity, and NH3 sources. Copy
it to create another versioned local profile; set a source's `mode` to `STATIC` for one publication
and process exit, or keep `PERIODIC` for fixed-delay publication until interrupted. MQTT settings
may be supplied with `--mqtt-host`, `--mqtt-port`, `--client-id`, timeout/attempt flags, or their
`PIGWATCH_SIMULATOR_*` environment equivalents. Run `uv run pigwatch-simulator --help` for the
complete command contract.

See [`docs/specs/m2-sensor-simulator.md`](docs/specs/m2-sensor-simulator.md) for determinism,
lifecycle, scheduling, provenance, failure, and retry semantics.

## M3 operator dashboard

Start the full dependency/API/dashboard stack, wait for readiness, and then run the M2 development
simulator in another terminal:

```bash
docker compose up -d --build --wait postgres mqtt api dashboard
curl --fail http://127.0.0.1:8000/health/ready
uv run pigwatch-simulator --config configs/simulator.development.json
```

Open `http://127.0.0.1:5173`. The dashboard shows API/ingestion dependency state, a factual summary
of the newest 200 observations, latest readings per source and measurement, separate origin and
delivery provenance, loaded-window filters, discrete historical points, and observation detail.
The default ten-second polling cycle never overlaps and the 60-second stale indication is a
dashboard freshness policy—not a biological threshold.

Dashboard build-time values are documented in [`.env.example`](.env.example) and
[`apps/dashboard/README.md`](apps/dashboard/README.md). The browser reads only the PigWatch API; it
does not connect to PostgreSQL or MQTT.

See [`docs/specs/m3-basic-dashboard.md`](docs/specs/m3-basic-dashboard.md) and
[`docs/known-limitations/m3.md`](docs/known-limitations/m3.md) for the complete contract and limits.

The initial Digital Farm is planned for M4 as a browser feature built with React, TypeScript,
Three.js, and React Three Fiber. No 3D engine dependency or rendering behavior is included in M3.

## Product guardrail

PigWatch outputs must be framed as observations, anomaly indications, and decision support. They must not claim that the system independently diagnoses disease or replaces a veterinarian.

## Roadmap

M0 established tooling and boundaries, M1 implements the accepted telemetry core, M2 adds the
environmental simulator, and M3 adds its read-only telemetry dashboard. The remaining milestone
sequence lives in
[docs/product/roadmap.md](docs/product/roadmap.md).
