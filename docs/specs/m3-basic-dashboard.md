# M3 Basic Dashboard Specification

## Status

Implementation specification for M3. This milestone consumes the accepted M1 telemetry and health
contracts and presents M2 observations without adding analytics, inferred state, or animal-health
semantics. ADR-0001 through ADR-0005 remain unchanged.

## Objective

M3 gives a local developer or operator a truthful, read-only view of PigWatch's current telemetry
path. At a glance, the user can determine whether the API and ingestion dependencies are ready,
whether observations are arriving, which sources and measurement types are represented, when the
latest evidence occurred, and the independent origin and delivery provenance of that evidence.

The product path remains:

```text
M2 simulators -> MQTT -> M1 ingestion -> PostgreSQL -> M1 API -> M3 dashboard
```

The browser communicates only with the PigWatch API. It never connects to PostgreSQL or MQTT.

## Scope

M3 includes:

- API liveness, ingestion readiness, PostgreSQL, and MQTT status using the existing health routes;
- a factual summary of the bounded observations currently loaded;
- latest-reading cards derived for every represented source and measurement pair;
- a filterable observation table and in-context observation detail dialog;
- explicit origin and delivery labels that never collapse provenance into one status;
- source, measurement, and loaded-window time filtering;
- bounded HTTP polling, manual refresh, and a factual freshness indication;
- a lightweight point-based time-series view of one loaded source/measurement series;
- responsive presentation and practical keyboard/screen-reader behavior; and
- component, API-client, polling, filtering, detail, and state tests.

## Non-goals

M3 does not include animal records or cards, physiology, health scores, disease detection,
threshold interpretation, anomaly detection, predictions, recommendations, alerts, Telegram,
voice, LLM/RAG, cameras, computer vision, RFID, thermal data, sensor fusion, sensor configuration,
real-hardware configuration, farm geometry, spatial placement, Three.js, React Three Fiber, or any
other M4+ behavior.

The dashboard reports evidence and infrastructure state. It does not label a measurement healthy,
dangerous, safe, unsafe, normal, or abnormal.

## Information architecture

The single dashboard page has the following order:

1. a compact product header with last successful observation refresh and manual refresh;
2. system status for API liveness, telemetry readiness, PostgreSQL, and MQTT;
3. a factual telemetry summary for loaded observations, distinct sources, and newest event time;
4. latest readings for each represented source/measurement pair;
5. source, measurement, and time-range filters with an explicit reset action;
6. a supplemental historical point plot for a selected visible series;
7. the bounded observation list; and
8. an in-context detail dialog for the selected observation.

## API usage

The dashboard has one typed client boundary. It retrieves:

- `GET /health/live`;
- `GET /health/ready`; and
- `GET /v1/observations?limit=200&order=desc`.

The API base URL defaults to `/api` and can be set at build time with
`VITE_PIGWATCH_API_BASE_URL`. Vite and the production Nginx image proxy the default relative path
to the API, avoiding direct database/broker exposure and avoiding a cross-origin browser contract.

M1's list endpoint currently returns the oldest rows first, so its bounded response cannot reliably
provide the latest observation once more rows exist than the requested limit. M3 adds only the
optional `order=desc` query value. The existing default remains ascending, the response model is
unchanged, and all existing callers preserve their behavior. This is a retrieval usability
extension, not an analytics endpoint or a telemetry schema change.

The client validates all response structures at runtime before exposing typed values to React.
Unexpected status codes, invalid JSON, missing fields, invalid enums, non-finite values, incoherent
payload/unit combinations, and invalid timestamps are explicit request failures. Observation
results remain capped by the M1 maximum of 500; the M3 default is 200.

## Refresh model

The default poll interval is 10 seconds and is configurable at build time with
`VITE_PIGWATCH_POLL_INTERVAL_MS`. Each cycle requests liveness, readiness, and observations.
Readiness HTTP 503 is parsed as a valid dependency state rather than treated as a malformed API
failure.

Polling uses a completion-scheduled timer rather than `setInterval`, so requests never overlap and
a slow or failed cycle cannot create a retry storm. The refresh control is disabled while a cycle
is active. Background tabs skip scheduled network refreshes and refresh promptly when visible
again. Unmount clears the timer, removes the visibility listener, and aborts active fetches.

Successful observation retrieval updates the displayed data and “last refreshed” time. A later
failure preserves prior observations and identifies them as last-known data.

## Presentation states

### Loading

The first observation request is pending. The page retains its structure, status controls, and
purposeful loading placeholders instead of showing a blank screen.

### Empty

The API returned a valid empty observation list. The page explains that no persisted observations
are in the loaded window and points the local operator to the M2 startup path without implying a
sensor or animal-health failure.

### Filtered empty

Observations are loaded but none match the active filters. The filter state remains visible and a
reset action is available.

### Stale data

When the newest loaded `event_time` is older than the dashboard freshness policy, the page states
that telemetry has not changed within that policy. The default threshold is 60 seconds and is
configurable with `VITE_PIGWATCH_STALE_AFTER_MS`. Freshness is an operator-dashboard timing policy,
not a biological threshold or health conclusion.

### API error

When observations cannot be retrieved and no prior data exists, the observation region presents
an explicit API error and retry action. Health request failures are shown independently.

### Dependency unavailable

A valid readiness response with `status=not_ready` is presented as ingestion unavailable, with the
PostgreSQL and MQTT booleans shown separately. Liveness remains independent.

### Partial data

Successful requests remain useful when another request fails. Previously retrieved observations
remain visible after a later observation failure, labeled as last-known data. Health failures do
not erase telemetry, and telemetry failures do not fabricate health dependency state.

## Telemetry presentation

Known payload discriminators receive readable labels while the exact discriminator remains
available in detail. Units are displayed exactly as stored (`Cel`, `%`, or `[ppm]`); no conversion
or threshold annotation occurs. Values are formatted for legibility without changing the stored
value shown in detail.

Latest-reading cards are derived by comparing event timestamps for every loaded
source/measurement pair. They are not hard-coded to the three development source IDs. Each card
contains value, unit, source ID, readable measurement, event time, ingest time, origin, and
delivery.

The table displays event time, source, measurement, value, unit, origin, and delivery. Selecting a
row opens factual metadata: event ID, schema version, event/ingest/replay time, topic, payload,
quality, trace, processing outcome, late flag, and clock-skew flag when exposed by M1.

## Filtering

Filters operate client-side over the bounded newest-first response:

- source ID;
- payload/measurement type; and
- event time within all loaded data, 15 minutes, 1 hour, 6 hours, or 24 hours.

Controls show their selected values, an active-filter count, and a reset action. Options come from
retrieved observations. Filtering does not claim to search rows beyond the loaded maximum and is
documented as bounded-window behavior. URL persistence is deferred to avoid introducing routing or
history synchronization complexity for this single page.

## Provenance presentation

Origin and delivery are always separate labeled badges in latest readings, table rows, and detail.
`SYNTHETIC` is never renamed or hidden. Current M2 readings therefore visibly show both
`SYNTHETIC` and `LIVE`. Color supports scanning but text provides the status.

## Historical visualization

The history view uses an inline SVG with actual event-time/value points from one visible
source/measurement series. It does not add a chart dependency, interpolate missing evidence,
create thresholds, highlight anomalies, or join unlike units. Source, measurement, unit, event
range, latest value, and point count are stated in text. Exact plotted observations also remain in
the table, so the chart is never the sole representation.

## Accessibility

The dashboard uses semantic landmarks, headings, tables, field labels, buttons, and status text.
Controls are keyboard accessible with visible focus treatment. The detail surface is a labeled
modal dialog that supports Escape, focuses its close control, and restores focus on close. Status
never depends only on color. The point plot has a descriptive accessible label and the table
retains exact values. Reduced-motion preferences disable non-essential transitions.

M3 makes practical accessibility provisions but does not claim formal WCAG certification.

## Responsiveness

Desktop is primary. Content uses bounded fluid columns and compact cards at laptop/tablet widths.
At narrow widths, controls and summary cards stack, the latest-reading grid becomes one column,
and the observation table remains available through labeled horizontal overflow rather than
discarding fields. The detail dialog becomes a full-height bottom-aligned surface.

## Performance limits

The client loads 200 observations by default and never requests more than M1's 500-row cap.
Derivations are bounded linear passes over the loaded result, and the filtered result and chart
series use local memoization where it avoids repeated work. The SVG plots at most the bounded
loaded result. No global state library, streaming connection, analytics store, or speculative M4
abstraction is introduced.

## Polling cleanup

Only one refresh promise and one `AbortController` are active. A successful or failed cycle
schedules exactly one later timer. Unmount marks the hook disposed, clears that timer, aborts the
controller, removes visibility handling, and prevents late state updates. React Strict Mode cleanup
therefore cannot leave an orphan poller.

## Testing strategy

Vitest and React Testing Library cover:

- typed client success for health and observations, HTTP failure, malformed responses, and abort;
- loading, empty, filtered-empty, unavailable, API-error, partial-data, and stale states;
- values, units, source IDs, timestamps, and separate origin/delivery rendering;
- source, measurement, time, and reset filtering;
- selection and factual observation detail, including live/recorded replay-time behavior;
- manual refresh, polling cadence, non-overlap, background behavior, and unmount cleanup; and
- history series selection, units, empty state, and absence of fabricated thresholds.

Python tests preserve the existing query default and verify the additive descending-order option.
The full M1/M2 non-integration and real PostgreSQL/Mosquitto suites remain regression protection.
A fresh Compose smoke starts PostgreSQL, MQTT, API, and dashboard, runs the real M2 simulator,
retrieves the resulting observations through the API, renders the dashboard in a browser, and
verifies cleanup.

## Acceptance criteria

M3 is acceptable when:

1. the dashboard reads telemetry only through the PigWatch API;
2. API liveness, readiness, PostgreSQL, and MQTT states are truthful and separately represented;
3. latest readings, values, units, source IDs, event times, and ingest times render from actual
   stored observations;
4. origin and delivery remain separate everywhere, including obvious `SYNTHETIC` + `LIVE` labels;
5. bounded observation listing, source/measurement/time filtering, reset, and filtered-empty state
   work;
6. the detail dialog renders every factual M1 field and replay time is truthful for both delivery
   modes;
7. loading, empty, stale, API-error, dependency-unavailable, and partial-data states are explicit;
8. polling is bounded, non-overlapping, background-safe, manually refreshable, and cleaned up;
9. the supplemental historical plot uses only actual like-unit observations and exact values remain
   textually available;
10. desktop, tablet, and narrow layouts retain usable content and keyboard focus is visible;
11. frontend tests and production build, Python quality and tests, Docker builds, Compose
    validation, real M1/M2 integration tests, and the M2-to-dashboard product smoke pass;
12. documentation and known limitations match implemented behavior;
13. no veterinary interpretation, credentials, paid service, LLM, or direct PostgreSQL/MQTT browser
    access is introduced; and
14. no M4+ behavior or dependency is introduced.

## Known limitations

- M3 is read-only and has no sensor configuration or control behavior.
- The history is the newest bounded API result, not a paginated or complete historical archive.
- Refresh uses polling rather than streaming and may miss intermediate display states.
- Freshness is evaluated from the newest loaded event time against the browser clock.
- Client-side filters search only the loaded bounded result and are not stored in the URL.
- Optimized labels and scalar presentation cover only the three payload types accepted by M1.
- There is no animal state, health interpretation, anomaly detection, alerting, spatial/3D view, or
  production authentication.
- Local API/dashboard proxy configuration is development-oriented; production deployment and
  access-control architecture remain undefined.
