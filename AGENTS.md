# AGENTS.md

## Mission

Build PigWatch as simulation-first livestock-health decision support. Report observations and anomalies; never present PigWatch as independently diagnosing veterinary disease.

## Before making changes

- Read this file, `ARCHITECTURE.md`, and the relevant feature specification and ADRs.
- Inspect existing interfaces before adding new ones; avoid changing public/shared contracts unnecessarily.
- Work on a task branch/worktree, keep the milestone boundary explicit, and inspect the working tree for user-owned changes.
- Preserve orthogonal source origin (`SYNTHETIC`/`PHYSICAL`) and delivery (`LIVE`/`RECORDED`) provenance, and keep simulation ground truth, observations, and inferred state separate.

## Allowed without additional approval

Within task scope, agents may inspect and edit repository files, create tests and fixtures, run local tests, linters, builds, and Docker, perform safe refactoring, and create commits on task branches.

## Requires explicit approval

Agents must not merge or push directly to `main`, force push, delete important branches, deploy external infrastructure, incur paid API/cloud costs, commit secrets, modify production credentials, or silently change global architecture or public/shared schemas.

Ed is the Product Owner. Flag decisions for Ed when they materially affect long-term architecture, infrastructure cost, paid services, major dependencies, public/shared schemas, the security model, deployment strategy, or product behavior.

Do not hide unfinished work behind `TODO` or `FIXME`. Document significant unresolved work in `docs/known-limitations/` or an active execution plan.

## Core commands

```bash
uv sync --all-packages --dev --locked
uv run ruff check .
uv run ruff format --check .
uv run mypy services packages tests
uv run pytest
npm ci
npm run check
docker compose config --quiet
```

## Definition of done

Before completing work:

- run the formatter and linter;
- run applicable type checks, tests, and builds;
- update documentation when behavior changes;
- inspect `git diff` and `git status`;
- verify that no credentials or unintended milestone work were added; and
- report known limitations and any validation that could not run.
