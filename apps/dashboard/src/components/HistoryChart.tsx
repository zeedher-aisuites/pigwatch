import { useEffect, useMemo, useState } from "react";

import type { StoredObservation } from "../api/types";
import {
  compareObservationsAscending,
  formatTimestamp,
  formatValue,
  PAYLOAD_LABELS,
  seriesKey,
} from "../telemetry";

interface Series {
  key: string;
  source: string;
  measurement: StoredObservation["envelope"]["payload_type"];
  unit: StoredObservation["envelope"]["payload"]["unit"];
  observations: StoredObservation[];
}

function buildSeries(observations: StoredObservation[]): Series[] {
  const grouped = new Map<string, Series>();
  for (const observation of observations) {
    const key = seriesKey(observation);
    const existing = grouped.get(key);
    if (existing) {
      existing.observations.push(observation);
    } else {
      grouped.set(key, {
        key,
        source: observation.envelope.source.source_id,
        measurement: observation.envelope.payload_type,
        unit: observation.envelope.payload.unit,
        observations: [observation],
      });
    }
  }
  return [...grouped.values()]
    .map((series) => ({
      ...series,
      observations: series.observations.sort(compareObservationsAscending),
    }))
    .sort((left, right) => left.source.localeCompare(right.source));
}

function normalizedValue(value: number, minimum: number, maximum: number): number {
  if (minimum === maximum) {
    return 0.5;
  }

  let position: number;
  if (minimum < 0 && maximum > 0) {
    const scale = Math.max(Math.abs(minimum), Math.abs(maximum));
    const scaledMinimum = minimum / scale;
    const scaledMaximum = maximum / scale;
    position = (value / scale - scaledMinimum) / (scaledMaximum - scaledMinimum);
  } else {
    position = (value - minimum) / (maximum - minimum);
  }
  return Math.min(1, Math.max(0, Number.isFinite(position) ? position : 0.5));
}

function plotPoints(series: Series): {
  points: { x: number; y: number; label: string }[];
  min: number;
  max: number;
} {
  const width = 720;
  const height = 220;
  const horizontalPadding = 28;
  const verticalPadding = 24;
  const times = series.observations.map((item) => Date.parse(item.envelope.event_time));
  const values = series.observations.map((item) => item.envelope.payload.value);
  const minimumTime = Math.min(...times);
  const maximumTime = Math.max(...times);
  const minimumValue = Math.min(...values);
  const maximumValue = Math.max(...values);
  const timeSpan = maximumTime - minimumTime;
  const points = series.observations.map((item, index) => {
    const value = values[index];
    const time = times[index];
    const x =
      timeSpan === 0
        ? width / 2
        : horizontalPadding + ((time - minimumTime) / timeSpan) * (width - horizontalPadding * 2);
    const y =
      height -
      verticalPadding -
      normalizedValue(value, minimumValue, maximumValue) * (height - verticalPadding * 2);
    return {
      x,
      y,
      label: `${formatValue(value)} ${series.unit} at ${formatTimestamp(item.envelope.event_time)}`,
    };
  });
  return { points, min: minimumValue, max: maximumValue };
}

export function HistoryChart({ observations }: { observations: StoredObservation[] }) {
  const series = useMemo(() => buildSeries(observations), [observations]);
  const [selectedKey, setSelectedKey] = useState("");

  useEffect(() => {
    if (series.length === 0) {
      setSelectedKey("");
    } else if (!series.some((item) => item.key === selectedKey)) {
      setSelectedKey(series[0].key);
    }
  }, [selectedKey, series]);

  const selected = series.find((item) => item.key === selectedKey) ?? series[0];

  return (
    <section className="panel history-panel" aria-labelledby="history-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Observed history</p>
          <h2 id="history-title">Loaded readings over time</h2>
        </div>
        {series.length > 0 && (
          <label className="series-select">
            <span>Series</span>
            <select value={selected?.key ?? ""} onChange={(event) => setSelectedKey(event.target.value)}>
              {series.map((item) => (
                <option value={item.key} key={item.key}>
                  {item.source} · {PAYLOAD_LABELS[item.measurement]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {selected ? <PointPlot series={selected} /> : <HistoryEmptyState />}
    </section>
  );
}

function HistoryEmptyState() {
  return (
    <div className="history-empty" role="status">
      <span aria-hidden="true">···</span>
      <p>No observations match the active filters.</p>
      <small>Adjust or reset filters to view loaded history.</small>
    </div>
  );
}

function PointPlot({ series }: { series: Series }) {
  const { points, min, max } = plotPoints(series);
  const first = series.observations[0];
  const latest = series.observations[series.observations.length - 1];
  const label = `${PAYLOAD_LABELS[series.measurement]} for ${series.source}; ${points.length} observed points from ${formatTimestamp(first.envelope.event_time)} to ${formatTimestamp(latest.envelope.event_time)}; values ${formatValue(min)} to ${formatValue(max)} ${series.unit}`;

  return (
    <div className="plot-layout">
      <div className="plot-copy">
        <p>{PAYLOAD_LABELS[series.measurement]}</p>
        <strong>{series.source}</strong>
        <dl>
          <div>
            <dt>Latest</dt>
            <dd title={String(latest.envelope.payload.value)}>
              {formatValue(latest.envelope.payload.value)} {series.unit}
            </dd>
          </div>
          <div>
            <dt>Loaded range</dt>
            <dd title={`${String(min)} to ${String(max)}`}>
              {formatValue(min)}–{formatValue(max)} {series.unit}
            </dd>
          </div>
          <div>
            <dt>Points</dt>
            <dd>{points.length}</dd>
          </div>
        </dl>
      </div>
      <div className="plot-frame">
        <svg className="point-plot" viewBox="0 0 720 220" role="img" aria-label={label}>
          <line x1="28" y1="24" x2="28" y2="196" className="plot-axis" />
          <line x1="28" y1="196" x2="692" y2="196" className="plot-axis" />
          <line x1="28" y1="67" x2="692" y2="67" className="plot-gridline" />
          <line x1="28" y1="110" x2="692" y2="110" className="plot-gridline" />
          <line x1="28" y1="153" x2="692" y2="153" className="plot-gridline" />
          {points.map((point, index) => (
            <circle cx={point.x} cy={point.y} r="5" className="plot-point" key={`${point.x}-${index}`}>
              <title>{point.label}</title>
            </circle>
          ))}
        </svg>
        <div className="plot-timeline" aria-hidden="true">
          <span>{formatTimestamp(first.envelope.event_time)}</span>
          <span>{formatTimestamp(latest.envelope.event_time)}</span>
        </div>
        <p className="plot-caption">Discrete observations only. Exact values remain in the table below.</p>
      </div>
    </div>
  );
}
