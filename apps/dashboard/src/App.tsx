import { useCallback, useMemo, useState } from "react";

import { apiClient, type ApiClient } from "./api/client";
import type { StoredObservation } from "./api/types";
import { Filters } from "./components/Filters";
import { HistoryChart } from "./components/HistoryChart";
import { LatestReadings } from "./components/LatestReadings";
import { ObservationDetail } from "./components/ObservationDetail";
import { ObservationTable } from "./components/ObservationTable";
import { Summary } from "./components/Summary";
import { SystemStatus } from "./components/SystemStatus";
import { dashboardConfig } from "./config";
import {
  EMPTY_FILTERS,
  filterObservations,
  formatRelativeTime,
  formatTimestamp,
  newestEventTime,
  type ObservationFilters,
} from "./telemetry";
import { useTelemetry } from "./useTelemetry";

const systemNow = () => new Date();

export interface AppProps {
  client?: ApiClient;
  pollIntervalMs?: number;
  staleAfterMs?: number;
  now?: () => Date;
}

function StateNotice({
  tone,
  title,
  children,
}: {
  tone: "warning" | "error" | "info";
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`state-notice state-notice--${tone}`} role="status">
      <span className="state-notice__icon" aria-hidden="true">
        {tone === "error" ? "!" : tone === "warning" ? "△" : "i"}
      </span>
      <div>
        <h2>{title}</h2>
        <p>{children}</p>
      </div>
    </section>
  );
}

export function App({
  client = apiClient,
  pollIntervalMs = dashboardConfig.pollIntervalMs,
  staleAfterMs = dashboardConfig.staleAfterMs,
  now = systemNow,
}: AppProps) {
  const telemetry = useTelemetry(client, pollIntervalMs, now);
  const [filters, setFilters] = useState<ObservationFilters>(EMPTY_FILTERS);
  const [selectedObservation, setSelectedObservation] = useState<StoredObservation | null>(null);
  const currentTime = now();
  const filteredObservations = useMemo(
    () => filterObservations(telemetry.observations, filters, currentTime),
    [currentTime, filters, telemetry.observations],
  );
  const newest = newestEventTime(telemetry.observations);
  const stale =
    newest !== null && currentTime.getTime() - Date.parse(newest) > Math.max(0, staleAfterMs);
  const healthPartial = telemetry.livenessError !== null || telemetry.readinessError !== null;
  const closeDetail = useCallback(() => setSelectedObservation(null), []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#main-content" aria-label="PigWatch dashboard home">
          <span className="brand__mark" aria-hidden="true">
            PW
          </span>
          <span>
            <strong>PigWatch</strong>
            <small>Operations</small>
          </span>
        </a>
        <div className="topbar__meta">
          <span className="read-only-label">
            <span aria-hidden="true">●</span> Read only
          </span>
          <span className="last-refresh">
            <span>Last data refresh</span>
            <strong title={telemetry.lastObservationRefresh?.toISOString()}>
              {telemetry.lastObservationRefresh
                ? formatRelativeTime(telemetry.lastObservationRefresh, currentTime)
                : "Not yet"}
            </strong>
          </span>
          <button
            className="button button--primary"
            type="button"
            onClick={() => void telemetry.refresh()}
            disabled={telemetry.refreshing}
          >
            <span
              className={telemetry.refreshing ? "refresh-icon refresh-icon--active" : "refresh-icon"}
              aria-hidden="true"
            >
              ↻
            </span>
            {telemetry.refreshing ? "Refreshing" : "Refresh data"}
          </button>
        </div>
      </header>

      <main id="main-content" className="dashboard">
        <section className="page-intro" aria-labelledby="page-title">
          <div>
            <p className="eyebrow">M3 · Telemetry console</p>
            <h1 id="page-title">Operational evidence, clearly in view.</h1>
            <p>
              Inspect persisted environmental observations and ingestion readiness without health
              interpretation.
            </p>
          </div>
          <div className="scope-card">
            <span>Current scope</span>
            <strong>Newest {dashboardConfig.observationLimit} observations</strong>
            <small>Polled every {Math.round(pollIntervalMs / 1_000)} seconds</small>
          </div>
        </section>

        <SystemStatus telemetry={telemetry} />

        <div className="state-stack" aria-live="polite">
          {telemetry.readiness?.status === "not_ready" && (
            <StateNotice tone="error" title="Telemetry ingestion is not ready">
              The API is responding, but one or more required dependencies are unavailable. Status
              above identifies PostgreSQL and MQTT separately.
            </StateNotice>
          )}
          {healthPartial && (
            <StateNotice tone="warning" title="System status is partially unavailable">
              Telemetry remains visible where available. Health requests will be tried again on the
              next bounded refresh.
            </StateNotice>
          )}
          {telemetry.observationError !== null && telemetry.observations.length > 0 && (
            <StateNotice tone="warning" title="Showing last-known telemetry">
              The latest observation request failed: {telemetry.observationError}. Existing data has
              been preserved.
            </StateNotice>
          )}
          {stale && newest !== null && (
            <StateNotice tone="info" title="Telemetry has not changed recently">
              The newest loaded event occurred {formatRelativeTime(newest, currentTime)} at{" "}
              {formatTimestamp(newest)}. The dashboard freshness policy is{" "}
              {Math.round(staleAfterMs / 1_000)} seconds; this is not a biological or health
              threshold.
            </StateNotice>
          )}
        </div>

        {!telemetry.observationsLoaded ? (
          <LoadingState />
        ) : telemetry.observationError !== null && telemetry.observations.length === 0 ? (
          <ErrorState message={telemetry.observationError} onRetry={() => void telemetry.refresh()} />
        ) : telemetry.observations.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="telemetry-content">
            <Summary observations={telemetry.observations} now={currentTime} />
            <LatestReadings observations={telemetry.observations} now={currentTime} />
            <Filters observations={telemetry.observations} filters={filters} onChange={setFilters} />
            <HistoryChart observations={filteredObservations} />
            {filteredObservations.length === 0 ? (
              <FilteredEmptyState onReset={() => setFilters(EMPTY_FILTERS)} />
            ) : (
              <ObservationTable
                observations={filteredObservations}
                totalLoaded={telemetry.observations.length}
                onSelect={setSelectedObservation}
              />
            )}
          </div>
        )}
      </main>

      <footer className="footer">
        <p>
          PigWatch presents observations for decision support. It does not independently diagnose
          veterinary disease.
        </p>
        <span>Origin and delivery provenance are shown independently.</span>
      </footer>

      {selectedObservation !== null && (
        <ObservationDetail observation={selectedObservation} onClose={closeDetail} />
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <section className="panel primary-state" aria-labelledby="loading-title" aria-busy="true">
      <div className="loading-bars" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="section-kicker">Initial request</p>
      <h2 id="loading-title">Loading persisted observations</h2>
      <p>The dashboard is contacting the PigWatch API and preserving the page structure while it waits.</p>
    </section>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="panel primary-state primary-state--error" role="alert">
      <span className="primary-state__glyph" aria-hidden="true">
        !
      </span>
      <p className="section-kicker">Observation API error</p>
      <h2>Persisted telemetry could not be retrieved</h2>
      <p>{message}</p>
      <button className="button button--primary" type="button" onClick={onRetry}>
        Try again
      </button>
    </section>
  );
}

function EmptyState() {
  return (
    <section className="panel primary-state" role="status">
      <span className="primary-state__glyph primary-state__glyph--quiet" aria-hidden="true">
        0
      </span>
      <p className="section-kicker">API reachable · no rows returned</p>
      <h2>No persisted observations yet</h2>
      <p>
        Start the M2 development simulator after ingestion reports ready. New synthetic readings will
        appear on a later poll or manual refresh.
      </p>
      <code>uv run pigwatch-simulator --config configs/simulator.development.json</code>
    </section>
  );
}

function FilteredEmptyState({ onReset }: { onReset: () => void }) {
  return (
    <section className="panel primary-state primary-state--compact" role="status">
      <span className="primary-state__glyph primary-state__glyph--quiet" aria-hidden="true">
        ∅
      </span>
      <p className="section-kicker">Filtered result</p>
      <h2>No observations match these filters</h2>
      <p>The loaded evidence is still available. Adjust the controls or reset all active filters.</p>
      <button className="button button--quiet" type="button" onClick={onReset}>
        Reset filters
      </button>
    </section>
  );
}
