export type SourceOrigin = "SYNTHETIC" | "PHYSICAL";
export type SourceDelivery = "LIVE" | "RECORDED";

export type PayloadType =
  | "environment.temperature"
  | "environment.relative_humidity"
  | "environment.ammonia_concentration";

export type ObservationUnit = "Cel" | "%" | "[ppm]";

export interface SourceDescriptor {
  source_id: string;
  origin: SourceOrigin;
  delivery: SourceDelivery;
}

export interface QualityMetadata {
  status: "GOOD" | "UNCERTAIN" | "BAD";
  confidence: number | null;
  flags: string[];
}

export interface TraceMetadata {
  correlation_id: string | null;
  trace_id: string | null;
}

export interface ObservationEnvelope {
  event_id: string;
  schema_version: "1.0";
  source: SourceDescriptor;
  event_time: string;
  replay_time: string | null;
  ingest_time: string;
  payload_type: PayloadType;
  payload: {
    value: number;
    unit: ObservationUnit;
  };
  quality: QualityMetadata | null;
  trace: TraceMetadata | null;
}

export interface StoredObservation {
  envelope: ObservationEnvelope;
  topic: string;
  is_late: boolean;
  clock_skew_detected: boolean;
  processing_outcome: "ACCEPTED";
}

export interface ObservationListResponse {
  items: StoredObservation[];
  count: number;
}

export interface LivenessResponse {
  status: "ok";
  service: "pigwatch-api";
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  service: "pigwatch-api";
  dependencies: {
    postgresql: boolean;
    mqtt: boolean;
  };
}
