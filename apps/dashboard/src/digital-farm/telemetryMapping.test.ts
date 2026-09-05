import { describe, expect, it } from "vitest";

import { makeObservation } from "../test/fixtures";
import { DEVELOPMENT_FARM_LAYOUT } from "./layout";
import { latestObservationForPlacement, mapFarmTelemetry } from "./telemetryMapping";

describe("M4 telemetry-to-placement mapping", () => {
  it("preserves the latest matching measurement, unit, and provenance", () => {
    const older = makeObservation({ value: 20, eventTime: "2026-09-04T11:59:00Z" });
    const latest = makeObservation({
      eventId: "0199483f-0200-7000-8000-000000000010",
      value: 22.75,
      eventTime: "2026-09-04T12:00:00Z",
      origin: "PHYSICAL",
      delivery: "RECORDED",
      replayTime: "2026-09-04T12:00:30Z",
    });

    const mapped = mapFarmTelemetry(DEVELOPMENT_FARM_LAYOUT, [latest, older]);
    const reading = mapped.bySourceId.get("sim-temperature-1");

    expect(reading?.observation).toBe(latest);
    expect(reading?.observation?.envelope.payload).toEqual({ value: 22.75, unit: "Cel" });
    expect(reading?.observation?.envelope.source).toEqual({
      source_id: "sim-temperature-1",
      origin: "PHYSICAL",
      delivery: "RECORDED",
    });
  });

  it("uses the M3 event-id tiebreaker for equal event times", () => {
    const first = makeObservation({
      eventId: "0199483f-0200-7000-8000-000000000001",
      value: 21,
    });
    const second = makeObservation({
      eventId: "0199483f-0200-7000-8000-000000000002",
      value: 22,
    });

    expect(
      latestObservationForPlacement(DEVELOPMENT_FARM_LAYOUT.sensors[0], [second, first]),
    ).toBe(second);
  });

  it("represents placed sources without matching telemetry and ignores mismatched payloads", () => {
    const mismatched = makeObservation({
      sourceId: "sim-temperature-1",
      payloadType: "environment.relative_humidity",
    });
    const mapped = mapFarmTelemetry(DEVELOPMENT_FARM_LAYOUT, [mismatched]);

    expect(mapped.bySourceId.get("sim-temperature-1")?.observation).toBeNull();
    expect(mapped.bySourceId.get("sim-humidity-1")?.observation).toBeNull();
  });

  it("reports telemetry source identities that have no placement without discarding them", () => {
    const unplaced = makeObservation({ sourceId: "future-environment-source" });
    const placed = makeObservation();
    const mapped = mapFarmTelemetry(DEVELOPMENT_FARM_LAYOUT, [unplaced, unplaced, placed]);

    expect(mapped.unplacedSourceIds).toEqual(["future-environment-source"]);
    expect(mapped.bySourceId.get("sim-temperature-1")?.observation).toBe(placed);
  });
});
