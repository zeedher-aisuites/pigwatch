# AGENTS.md

## Mission

Build PigWatch as simulation-first livestock-health decision support. Report observations and anomalies; never present PigWatch as independently diagnosing veterinary disease.

## Working rules

- Work on a task branch/worktree; never commit directly to `main`.
- Read `ARCHITECTURE.md` and relevant ADRs/specs before changing boundaries.
- Keep simulated, recorded, and live inputs behind the same capability-specific interfaces.
- Preserve provenance and distinguish ground truth from observed state.
- Keep M0 free of M1+ product behavior and add large dependencies only when a milestone needs them.
- Never commit secrets. Update `.env.example` with placeholders when configuration changes.
- Document material architecture decisions in `docs/adr/`; record temporary gaps in `docs/known-limitations/`.
- Add or update tests with behavior changes. Run Python lint, format, type, and test checks plus dashboard checks before handoff.

## Core commands

```bash
uv sync --all-packages --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy services packages tests
uv run pytest
npm ci
npm run check
docker compose config --quiet
```

## Definition of done

The change is scoped, tested, documented, contains no credentials, reports known limitations, and leaves only intended files in `git status`.
