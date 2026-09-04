import type { PayloadType, StoredObservation } from "../api/types";
import {
  EMPTY_FILTERS,
  type ObservationFilters,
  PAYLOAD_LABELS,
  type TimeRange,
  TIME_RANGE_LABELS,
} from "../telemetry";

export function activeFilterCount(filters: ObservationFilters): number {
  return Number(filters.source !== "") +
    Number(filters.measurement !== "") +
    Number(filters.timeRange !== "all");
}

export function Filters({
  observations,
  filters,
  onChange,
}: {
  observations: StoredObservation[];
  filters: ObservationFilters;
  onChange: (filters: ObservationFilters) => void;
}) {
  const sources = [...new Set(observations.map((item) => item.envelope.source.source_id))].sort();
  const measurements = [
    ...new Set(observations.map((item) => item.envelope.payload_type)),
  ].sort();
  const activeCount = activeFilterCount(filters);

  return (
    <section className="filter-bar" aria-labelledby="filters-title">
      <div className="filter-bar__title">
        <div>
          <p className="section-kicker">Loaded-window controls</p>
          <h2 id="filters-title">Filter observations</h2>
        </div>
        <span className="filter-count" aria-live="polite">
          {activeCount === 0 ? "No active filters" : `${activeCount} active`}
        </span>
      </div>
      <div className="filter-controls">
        <label>
          <span>Source</span>
          <select
            value={filters.source}
            onChange={(event) => onChange({ ...filters, source: event.target.value })}
          >
            <option value="">All sources</option>
            {sources.map((source) => (
              <option value={source} key={source}>
                {source}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Measurement</span>
          <select
            value={filters.measurement}
            onChange={(event) =>
              onChange({ ...filters, measurement: event.target.value as PayloadType | "" })
            }
          >
            <option value="">All measurements</option>
            {measurements.map((measurement) => (
              <option value={measurement} key={measurement}>
                {PAYLOAD_LABELS[measurement]}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Event time</span>
          <select
            value={filters.timeRange}
            onChange={(event) =>
              onChange({ ...filters, timeRange: event.target.value as TimeRange })
            }
          >
            {(Object.keys(TIME_RANGE_LABELS) as TimeRange[]).map((range) => (
              <option value={range} key={range}>
                {TIME_RANGE_LABELS[range]}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button button--quiet filter-reset"
          type="button"
          disabled={activeCount === 0}
          onClick={() => onChange(EMPTY_FILTERS)}
        >
          Reset filters
        </button>
      </div>
      <p className="filter-bar__note">Filters apply to the newest bounded result loaded from the API.</p>
    </section>
  );
}
