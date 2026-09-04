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

M3 uses the existing bounded observation list and health routes. The optional `order=desc` query
value returns newest event time first for bounded dashboard retrieval; omitting it preserves M1's
ascending default. No telemetry response or storage schema changed.
