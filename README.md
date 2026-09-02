# PigWatch

PigWatch is a simulation-first livestock health monitoring platform. It is designed to detect and communicate physiological and behavioral anomalies; it is not an autonomous veterinary diagnostic system.

This repository currently contains the **M0 engineering foundation only**. Product telemetry, sensor simulation, computer-vision pipelines, anomaly detection, alerts, and hardware integrations belong to later milestones.

## Repository layout

```text
apps/dashboard/          React + TypeScript operator dashboard shell
services/api/            FastAPI service and health endpoints
packages/python/         Shared Python schemas, source contracts, and package seams
simulators/godot/        Reserved boundary for the future Godot digital farm
infra/                   Local infrastructure configuration
tests/                   Cross-package Python tests
docs/                    Product, architecture, ADR, specification, and plan records
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for system boundaries and [AGENTS.md](AGENTS.md) for repository working rules.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and npm
- Docker with Docker Compose (optional for local infrastructure)

## First-time setup

```bash
uv sync --all-packages --dev
npm ci
```

Copy `.env.example` to `.env` and replace every placeholder before starting Docker services. `.env` is ignored by Git.

## Development commands

Run the API:

```bash
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

Run the local stack after configuring `.env`:

```bash
docker compose up --build
```

The dashboard is served at `http://localhost:5173`; API health endpoints are at `http://localhost:8000/health/live` and `/health/ready`.

## Product guardrail

PigWatch outputs must be framed as observations, anomaly indications, and decision support. They must not claim that the system independently diagnoses disease or replaces a veterinarian.

## Roadmap

M0 establishes tooling and boundaries. The next milestone, M1, is the telemetry core. The complete milestone sequence and exit criteria live in [docs/product/roadmap.md](docs/product/roadmap.md).
