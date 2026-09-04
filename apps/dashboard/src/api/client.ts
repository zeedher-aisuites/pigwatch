import { dashboardConfig } from "../config";
import type {
  LivenessResponse,
  ObservationEnvelope,
  ObservationListResponse,
  PayloadType,
  QualityMetadata,
  ReadinessResponse,
  SourceDelivery,
  SourceOrigin,
  StoredObservation,
  TraceMetadata,
} from "./types";

export interface ApiClient {
  getLiveness(signal?: AbortSignal): Promise<LivenessResponse>;
  getReadiness(signal?: AbortSignal): Promise<ReadinessResponse>;
  getObservations(signal?: AbortSignal): Promise<ObservationListResponse>;
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, label: string): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new ApiRequestError(`${label} must be an object`);
  }
  return value;
}

function requireString(value: unknown, label: string): string {
  if (typeof value !== "string" || value.length === 0) {
    throw new ApiRequestError(`${label} must be a non-empty string`);
  }
  return value;
}

function requireTimestamp(value: unknown, label: string): string {
  const timestamp = requireString(value, label);
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/.exec(
    timestamp,
  );
  if (match === null) {
    throw new ApiRequestError(`${label} must be a timezone-aware RFC 3339 timestamp`);
  }

  const [, yearText, monthText, dayText, hourText, minuteText, secondText, offset] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const offsetHour = offset === "Z" ? 0 : Number(offset.slice(1, 3));
  const offsetMinute = offset === "Z" ? 0 : Number(offset.slice(4, 6));
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const monthLengths = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  const daysInMonth = month >= 1 && month <= 12 ? monthLengths[month - 1] : 0;

  if (
    month < 1 ||
    month > 12 ||
    day < 1 ||
    day > daysInMonth ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59 ||
    !Number.isFinite(Date.parse(timestamp))
  ) {
    throw new ApiRequestError(`${label} must be a valid timezone-aware RFC 3339 timestamp`);
  }
  return timestamp;
}

function requireBoolean(value: unknown, label: string): boolean {
  if (typeof value !== "boolean") {
    throw new ApiRequestError(`${label} must be a boolean`);
  }
  return value;
}

function requireNullableString(value: unknown, label: string): string | null {
  return value === null ? null : requireString(value, label);
}

function parseOrigin(value: unknown): SourceOrigin {
  if (value !== "SYNTHETIC" && value !== "PHYSICAL") {
    throw new ApiRequestError("source.origin is invalid");
  }
  return value;
}

function parseDelivery(value: unknown): SourceDelivery {
  if (value !== "LIVE" && value !== "RECORDED") {
    throw new ApiRequestError("source.delivery is invalid");
  }
  return value;
}

function parsePayloadType(value: unknown): PayloadType {
  if (
    value !== "environment.temperature" &&
    value !== "environment.relative_humidity" &&
    value !== "environment.ammonia_concentration"
  ) {
    throw new ApiRequestError("envelope.payload_type is unsupported");
  }
  return value;
}

function parseQuality(value: unknown): QualityMetadata | null {
  if (value === null) {
    return null;
  }
  const quality = requireRecord(value, "envelope.quality");
  if (quality.status !== "GOOD" && quality.status !== "UNCERTAIN" && quality.status !== "BAD") {
    throw new ApiRequestError("envelope.quality.status is invalid");
  }
  if (
    quality.confidence !== null &&
    (typeof quality.confidence !== "number" ||
      !Number.isFinite(quality.confidence) ||
      quality.confidence < 0 ||
      quality.confidence > 1)
  ) {
    throw new ApiRequestError("envelope.quality.confidence is invalid");
  }
  if (!Array.isArray(quality.flags) || quality.flags.some((flag) => typeof flag !== "string")) {
    throw new ApiRequestError("envelope.quality.flags is invalid");
  }
  return {
    status: quality.status,
    confidence: quality.confidence as number | null,
    flags: quality.flags as string[],
  };
}

function parseTrace(value: unknown): TraceMetadata | null {
  if (value === null) {
    return null;
  }
  const trace = requireRecord(value, "envelope.trace");
  const correlationId = requireNullableString(trace.correlation_id, "trace.correlation_id");
  const traceId = requireNullableString(trace.trace_id, "trace.trace_id");
  if (correlationId === null && traceId === null) {
    throw new ApiRequestError("envelope.trace requires an identifier");
  }
  return { correlation_id: correlationId, trace_id: traceId };
}

function parseEnvelope(value: unknown): ObservationEnvelope {
  const envelope = requireRecord(value, "observation.envelope");
  const source = requireRecord(envelope.source, "envelope.source");
  const payload = requireRecord(envelope.payload, "envelope.payload");
  const payloadType = parsePayloadType(envelope.payload_type);
  const sourceDelivery = parseDelivery(source.delivery);
  const replayTime =
    envelope.replay_time === null
      ? null
      : requireTimestamp(envelope.replay_time, "envelope.replay_time");
  if (
    (sourceDelivery === "LIVE" && replayTime !== null) ||
    (sourceDelivery === "RECORDED" && replayTime === null)
  ) {
    throw new ApiRequestError("envelope replay time does not match source delivery");
  }
  if (typeof payload.value !== "number" || !Number.isFinite(payload.value)) {
    throw new ApiRequestError("envelope.payload.value must be finite");
  }
  const expectedUnits = {
    "environment.temperature": "Cel",
    "environment.relative_humidity": "%",
    "environment.ammonia_concentration": "[ppm]",
  } as const;
  const expectedUnit = expectedUnits[payloadType];
  if (payload.unit !== expectedUnit) {
    throw new ApiRequestError("envelope payload unit does not match payload type");
  }
  if (envelope.schema_version !== "1.0") {
    throw new ApiRequestError("envelope.schema_version is unsupported");
  }
  return {
    event_id: requireString(envelope.event_id, "envelope.event_id"),
    schema_version: envelope.schema_version,
    source: {
      source_id: requireString(source.source_id, "source.source_id"),
      origin: parseOrigin(source.origin),
      delivery: sourceDelivery,
    },
    event_time: requireTimestamp(envelope.event_time, "envelope.event_time"),
    replay_time: replayTime,
    ingest_time: requireTimestamp(envelope.ingest_time, "envelope.ingest_time"),
    payload_type: payloadType,
    payload: { value: payload.value, unit: expectedUnit },
    quality: parseQuality(envelope.quality),
    trace: parseTrace(envelope.trace),
  };
}

function parseStoredObservation(value: unknown): StoredObservation {
  const observation = requireRecord(value, "observation");
  if (observation.processing_outcome !== "ACCEPTED") {
    throw new ApiRequestError("observation.processing_outcome is invalid");
  }
  return {
    envelope: parseEnvelope(observation.envelope),
    topic: requireString(observation.topic, "observation.topic"),
    is_late: requireBoolean(observation.is_late, "observation.is_late"),
    clock_skew_detected: requireBoolean(
      observation.clock_skew_detected,
      "observation.clock_skew_detected",
    ),
    processing_outcome: observation.processing_outcome,
  };
}

export function parseObservationList(
  value: unknown,
  requestedLimit = 500,
): ObservationListResponse {
  const response = requireRecord(value, "observation response");
  if (!Array.isArray(response.items)) {
    throw new ApiRequestError("observation response items must be an array");
  }
  if (!Number.isInteger(response.count) || (response.count as number) < 0) {
    throw new ApiRequestError("observation response count must be a non-negative integer");
  }
  const boundedLimit = Math.min(500, Math.max(1, Math.trunc(requestedLimit)));
  const count = response.count as number;
  if (response.items.length > 500 || count > 500) {
    throw new ApiRequestError("observation response exceeds the absolute limit of 500 items");
  }
  if (response.items.length > boundedLimit || count > boundedLimit) {
    throw new ApiRequestError(
      `observation response exceeds the requested limit of ${boundedLimit} items`,
    );
  }
  if (count !== response.items.length) {
    throw new ApiRequestError("observation response count does not match its items");
  }
  const items = response.items.map(parseStoredObservation);
  return { items, count };
}

export function parseLiveness(value: unknown): LivenessResponse {
  const response = requireRecord(value, "liveness response");
  if (response.status !== "ok" || response.service !== "pigwatch-api") {
    throw new ApiRequestError("liveness response is invalid");
  }
  return { status: response.status, service: response.service };
}

export function parseReadiness(value: unknown): ReadinessResponse {
  const response = requireRecord(value, "readiness response");
  const dependencies = requireRecord(response.dependencies, "readiness dependencies");
  if (
    (response.status !== "ready" && response.status !== "not_ready") ||
    response.service !== "pigwatch-api"
  ) {
    throw new ApiRequestError("readiness response is invalid");
  }
  const postgresql = requireBoolean(dependencies.postgresql, "dependencies.postgresql");
  const mqtt = requireBoolean(dependencies.mqtt, "dependencies.mqtt");
  if ((response.status === "ready") !== (postgresql && mqtt)) {
    throw new ApiRequestError("readiness status does not match dependency state");
  }
  return {
    status: response.status,
    service: response.service,
    dependencies: { postgresql, mqtt },
  };
}

async function responseBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch (error) {
    throw new ApiRequestError("PigWatch API returned invalid JSON", response.status) as Error & {
      cause?: unknown;
    };
  }
}

function failureDetail(value: unknown): string | null {
  if (!isRecord(value) || typeof value.detail !== "string") {
    return null;
  }
  return value.detail;
}

export function createApiClient(
  baseUrl = dashboardConfig.apiBaseUrl,
  observationLimit = dashboardConfig.observationLimit,
): ApiClient {
  const boundedLimit = Math.min(500, Math.max(1, Math.trunc(observationLimit)));

  async function get(
    path: string,
    signal: AbortSignal | undefined,
    acceptedStatuses: readonly number[] = [200],
  ): Promise<unknown> {
    let response: Response;
    try {
      response = await fetch(`${baseUrl}${path}`, {
        headers: { Accept: "application/json" },
        signal,
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      throw new ApiRequestError("PigWatch API could not be reached") as Error & { cause?: unknown };
    }
    const body = await responseBody(response);
    if (!acceptedStatuses.includes(response.status)) {
      const detail = failureDetail(body);
      throw new ApiRequestError(detail ?? `PigWatch API returned HTTP ${response.status}`, response.status);
    }
    return body;
  }

  return {
    async getLiveness(signal) {
      return parseLiveness(await get("/health/live", signal));
    },
    async getReadiness(signal) {
      return parseReadiness(await get("/health/ready", signal, [200, 503]));
    },
    async getObservations(signal) {
      return parseObservationList(
        await get(`/v1/observations?limit=${boundedLimit}&order=desc`, signal),
        boundedLimit,
      );
    },
  };
}

export const apiClient = createApiClient();
