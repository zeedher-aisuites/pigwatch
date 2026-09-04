# PigWatch Dashboard

The M3 dashboard is a read-only React/TypeScript operator view for persisted PigWatch telemetry.
It displays API and ingestion readiness, the newest bounded observation window, latest readings,
independent origin/delivery provenance, filters, factual detail, and discrete historical points.
It does not interpret animal or environmental health.

## Run locally

Start PostgreSQL, MQTT, and the API, then run Vite from the repository root:

```bash
docker compose up -d --wait postgres mqtt api
npm run dev --workspace @pigwatch/dashboard
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`.

To produce the M2 development readings after `/health/ready` succeeds:

```bash
uv run pigwatch-simulator --config configs/simulator.development.json
```

Alternatively, build and run the full stack:

```bash
docker compose up --build
```

The Nginx dashboard image proxies `/api` to the Compose API service. The browser never connects to
PostgreSQL or MQTT.

## Configuration

Vite configuration is embedded at build time:

| Variable | Default | Constraint |
| --- | --- | --- |
| `VITE_PIGWATCH_API_BASE_URL` | `/api` | Relative proxy path is recommended locally |
| `VITE_PIGWATCH_OBSERVATION_LIMIT` | `200` | 1 through the API maximum of 500 |
| `VITE_PIGWATCH_POLL_INTERVAL_MS` | `10000` | 1,000 through 300,000 ms |
| `VITE_PIGWATCH_STALE_AFTER_MS` | `60000` | 10,000 through 86,400,000 ms |

Invalid numeric configuration falls back to its documented default. Polling waits for each cycle
to settle before scheduling the next, pauses scheduled requests while the page is hidden, and
aborts active requests on unmount. Manual refresh is available from the header.

The stale indication is an operator-dashboard freshness policy based on the newest loaded event
time and browser clock. It is not a health or biological threshold.

## Filters and evidence window

Source, measurement, and time filters run in the browser over the newest bounded result returned by
the API. “All loaded” means that bounded result, not the complete database history. Reset filters
restores all sources, all measurements, and the entire loaded window.

Origin (`SYNTHETIC`/`PHYSICAL`) and delivery (`LIVE`/`RECORDED`) are displayed as separate labels in
reading cards, observation rows, and detail. Recorded evidence displays replay time; live evidence
states that replay time is not applicable.

## Validation

From the repository root:

```bash
npm run typecheck --workspace @pigwatch/dashboard
npm run test --workspace @pigwatch/dashboard
npm run build --workspace @pigwatch/dashboard
```

See [`docs/specs/m3-basic-dashboard.md`](../../docs/specs/m3-basic-dashboard.md) and
[`docs/known-limitations/m3.md`](../../docs/known-limitations/m3.md) for the complete behavior and
limits.
