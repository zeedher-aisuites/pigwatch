# PigWatch API

FastAPI application boundary for M1 dependency-aware health and minimal observation retrieval. The
same deployable owns the modular telemetry ingestion worker; M1 does not introduce a separate
microservice.

Run migrations before starting the API:

```bash
uv run alembic -c services/api/alembic.ini upgrade head
uv run --package pigwatch-api uvicorn pigwatch_api.main:app --reload
```

The initial migration has a destructive downgrade for isolated development/testing only. Production
deployment, authentication and retention remain outside M1.
