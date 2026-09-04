const DEFAULT_API_BASE_URL = "/api";
const DEFAULT_OBSERVATION_LIMIT = 200;
const DEFAULT_POLL_INTERVAL_MS = 10_000;
const DEFAULT_STALE_AFTER_MS = 60_000;

function readBoundedNumber(
  value: string | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  if (value === undefined || value.trim() === "") {
    return fallback;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum ? parsed : fallback;
}

function normalizeApiBaseUrl(value: string | undefined): string {
  const candidate = value?.trim() || DEFAULT_API_BASE_URL;
  return candidate === "/" ? "" : candidate.replace(/\/+$/, "");
}

export const dashboardConfig = Object.freeze({
  apiBaseUrl: normalizeApiBaseUrl(import.meta.env.VITE_PIGWATCH_API_BASE_URL),
  observationLimit: readBoundedNumber(
    import.meta.env.VITE_PIGWATCH_OBSERVATION_LIMIT,
    DEFAULT_OBSERVATION_LIMIT,
    1,
    500,
  ),
  pollIntervalMs: readBoundedNumber(
    import.meta.env.VITE_PIGWATCH_POLL_INTERVAL_MS,
    DEFAULT_POLL_INTERVAL_MS,
    1_000,
    300_000,
  ),
  staleAfterMs: readBoundedNumber(
    import.meta.env.VITE_PIGWATCH_STALE_AFTER_MS,
    DEFAULT_STALE_AFTER_MS,
    10_000,
    86_400_000,
  ),
});
