import type { StoredObservation } from "../api/types";
import { compareObservationsAscending } from "../telemetry";
import type { FarmLayout, SensorPlacement } from "./types";

export interface SpatialReading {
  placement: SensorPlacement;
  observation: StoredObservation | null;
}

export interface FarmTelemetryMapping {
  readings: readonly SpatialReading[];
  bySourceId: ReadonlyMap<string, SpatialReading>;
  unplacedSourceIds: readonly string[];
}

export function latestObservationForPlacement(
  placement: SensorPlacement,
  observations: readonly StoredObservation[],
): StoredObservation | null {
  let latest: StoredObservation | null = null;
  for (const observation of observations) {
    const envelope = observation.envelope;
    if (
      envelope.source.source_id === placement.sourceId &&
      envelope.payload_type === placement.payloadType &&
      (latest === null || compareObservationsAscending(observation, latest) > 0)
    ) {
      latest = observation;
    }
  }
  return latest;
}

export function mapFarmTelemetry(
  layout: FarmLayout,
  observations: readonly StoredObservation[],
): FarmTelemetryMapping {
  const readings = layout.sensors.map((placement) => ({
    placement,
    observation: latestObservationForPlacement(placement, observations),
  }));
  const bySourceId = new Map(readings.map((reading) => [reading.placement.sourceId, reading]));
  const placedSourceIds = new Set(layout.sensors.map((sensor) => sensor.sourceId));
  const unplacedSourceIds = [
    ...new Set(
      observations
        .map((observation) => observation.envelope.source.source_id)
        .filter((sourceId) => !placedSourceIds.has(sourceId)),
    ),
  ].sort();
  return { readings, bySourceId, unplacedSourceIds };
}
