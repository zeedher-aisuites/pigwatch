import type { PayloadType, StoredObservation } from "./api/types";

export type TimeRange = "all" | "15m" | "1h" | "6h" | "24h";

export interface ObservationFilters {
  source: string;
  measurement: PayloadType | "";
  timeRange: TimeRange;
}

export const EMPTY_FILTERS: ObservationFilters = {
  source: "",
  measurement: "",
  timeRange: "all",
};

export const PAYLOAD_LABELS: Record<PayloadType, string> = {
  "environment.temperature": "Air temperature",
  "environment.relative_humidity": "Relative humidity",
  "environment.ammonia_concentration": "NH3 concentration",
};

export const TIME_RANGE_LABELS: Record<TimeRange, string> = {
  all: "All loaded",
  "15m": "Last 15 minutes",
  "1h": "Last hour",
  "6h": "Last 6 hours",
  "24h": "Last 24 hours",
};

const TIME_RANGE_MS: Record<Exclude<TimeRange, "all">, number> = {
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "6h": 6 * 60 * 60_000,
  "24h": 24 * 60 * 60_000,
};

export function seriesKey(observation: StoredObservation): string {
  return `${observation.envelope.source.source_id}\u0000${observation.envelope.payload_type}`;
}

export function latestObservations(observations: StoredObservation[]): StoredObservation[] {
  const latest = new Map<string, StoredObservation>();
  for (const observation of observations) {
    const key = seriesKey(observation);
    const current = latest.get(key);
    if (
      current === undefined ||
      Date.parse(observation.envelope.event_time) > Date.parse(current.envelope.event_time)
    ) {
      latest.set(key, observation);
    }
  }
  return [...latest.values()].sort(
    (left, right) => Date.parse(right.envelope.event_time) - Date.parse(left.envelope.event_time),
  );
}

export function newestEventTime(observations: StoredObservation[]): string | null {
  let newest: string | null = null;
  for (const observation of observations) {
    if (newest === null || Date.parse(observation.envelope.event_time) > Date.parse(newest)) {
      newest = observation.envelope.event_time;
    }
  }
  return newest;
}

export function filterObservations(
  observations: StoredObservation[],
  filters: ObservationFilters,
  now: Date,
): StoredObservation[] {
  const cutoff =
    filters.timeRange === "all" ? null : now.getTime() - TIME_RANGE_MS[filters.timeRange];
  return observations.filter((observation) => {
    const envelope = observation.envelope;
    return (
      (filters.source === "" || envelope.source.source_id === filters.source) &&
      (filters.measurement === "" || envelope.payload_type === filters.measurement) &&
      (cutoff === null || Date.parse(envelope.event_time) >= cutoff)
    );
  });
}

export function formatValue(value: number): string {
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: 3,
    minimumFractionDigits: 0,
  }).format(value);
}

export function formatTimestamp(value: string | null): string {
  if (value === null) {
    return "Not applicable";
  }
  return `${new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value))} UTC`;
}

export function formatRelativeTime(value: string | Date, now: Date): string {
  const timestamp = typeof value === "string" ? Date.parse(value) : value.getTime();
  const deltaSeconds = Math.round((timestamp - now.getTime()) / 1_000);
  const absoluteSeconds = Math.abs(deltaSeconds);
  if (absoluteSeconds < 5) {
    return "just now";
  }
  const formatter = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (absoluteSeconds < 60) {
    return formatter.format(deltaSeconds, "second");
  }
  const deltaMinutes = Math.round(deltaSeconds / 60);
  if (Math.abs(deltaMinutes) < 60) {
    return formatter.format(deltaMinutes, "minute");
  }
  const deltaHours = Math.round(deltaMinutes / 60);
  if (Math.abs(deltaHours) < 24) {
    return formatter.format(deltaHours, "hour");
  }
  return formatter.format(Math.round(deltaHours / 24), "day");
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim() !== "") {
    return error.message;
  }
  return "An unexpected request failure occurred";
}
