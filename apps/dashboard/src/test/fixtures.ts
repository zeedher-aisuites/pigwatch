import type {
  LivenessResponse,
  ObservationListResponse,
  PayloadType,
  ReadinessResponse,
  SourceDelivery,
  SourceOrigin,
  StoredObservation,
} from "../api/types";

const payloadDefaults: Record<PayloadType, { value: number; unit: "Cel" | "%" | "[ppm]" }> = {
  "environment.temperature": { value: 22.4, unit: "Cel" },
  "environment.relative_humidity": { value: 64.2, unit: "%" },
  "environment.ammonia_concentration": { value: 8.1, unit: "[ppm]" },
};

interface ObservationOverrides {
  eventId?: string;
  sourceId?: string;
  origin?: SourceOrigin;
  delivery?: SourceDelivery;
  eventTime?: string;
  ingestTime?: string;
  replayTime?: string | null;
  payloadType?: PayloadType;
  value?: number;
  topic?: string;
  quality?: StoredObservation["envelope"]["quality"];
  trace?: StoredObservation["envelope"]["trace"];
  isLate?: boolean;
  clockSkewDetected?: boolean;
}

export function makeObservation(overrides: ObservationOverrides = {}): StoredObservation {
  const payloadType = overrides.payloadType ?? "environment.temperature";
  const delivery = overrides.delivery ?? "LIVE";
  const sourceId = overrides.sourceId ?? "sim-temperature-1";
  const replayTime =
    delivery === "RECORDED"
      ? (overrides.replayTime ?? "2026-09-04T12:00:30Z")
      : null;
  return {
    envelope: {
      event_id: overrides.eventId ?? "0199483f-0200-7000-8000-000000000001",
      schema_version: "1.0",
      source: {
        source_id: sourceId,
        origin: overrides.origin ?? "SYNTHETIC",
        delivery,
      },
      event_time: overrides.eventTime ?? "2026-09-04T12:00:00Z",
      replay_time: replayTime,
      ingest_time: overrides.ingestTime ?? "2026-09-04T12:00:01Z",
      payload_type: payloadType,
      payload: {
        value: overrides.value ?? payloadDefaults[payloadType].value,
        unit: payloadDefaults[payloadType].unit,
      },
      quality:
        overrides.quality === undefined
          ? { status: "GOOD", confidence: 0.98, flags: [] }
          : overrides.quality,
      trace: overrides.trace === undefined ? null : overrides.trace,
    },
    topic:
      overrides.topic ??
      `pigwatch/v1/observations/site/development-site/${sourceId}/temperature`,
    is_late: overrides.isLate ?? false,
    clock_skew_detected: overrides.clockSkewDetected ?? false,
    processing_outcome: "ACCEPTED",
  };
}

export const livenessReady: LivenessResponse = {
  status: "ok",
  service: "pigwatch-api",
};

export const dependenciesReady: ReadinessResponse = {
  status: "ready",
  service: "pigwatch-api",
  dependencies: { postgresql: true, mqtt: true },
};

export function observationResponse(items: StoredObservation[]): ObservationListResponse {
  return { items, count: items.length };
}
