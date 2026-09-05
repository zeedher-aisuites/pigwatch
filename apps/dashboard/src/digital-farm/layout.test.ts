import { describe, expect, it } from "vitest";

import { DEVELOPMENT_FARM_LAYOUT, validateFarmLayout } from "./layout";
import type { FarmLayout } from "./types";

function copyLayout(): FarmLayout {
  return structuredClone(DEVELOPMENT_FARM_LAYOUT);
}

describe("M4 development farm layout", () => {
  it("maps the three actual M2 source identities deterministically", () => {
    expect(DEVELOPMENT_FARM_LAYOUT.sensors).toEqual([
      expect.objectContaining({
        sourceId: "sim-temperature-1",
        zoneId: "pen-a",
        payloadType: "environment.temperature",
        position: [-8, 2.2, -2],
      }),
      expect.objectContaining({
        sourceId: "sim-humidity-1",
        zoneId: "pen-b",
        payloadType: "environment.relative_humidity",
        position: [8, 2.2, -2],
      }),
      expect.objectContaining({
        sourceId: "sim-nh3-1",
        zoneId: "service-aisle",
        payloadType: "environment.ammonia_concentration",
        position: [0, 2.2, 7],
      }),
    ]);
    expect(validateFarmLayout(DEVELOPMENT_FARM_LAYOUT)).toBe(DEVELOPMENT_FARM_LAYOUT);
  });

  it("rejects duplicate zone and source identities", () => {
    const duplicateZone = copyLayout();
    duplicateZone.zones = [...duplicateZone.zones, structuredClone(duplicateZone.zones[0])];
    expect(() => validateFarmLayout(duplicateZone)).toThrow("duplicate zone id: pen-a");

    const duplicateSensor = copyLayout();
    duplicateSensor.sensors = [
      ...duplicateSensor.sensors,
      structuredClone(duplicateSensor.sensors[0]),
    ];
    expect(() => validateFarmLayout(duplicateSensor)).toThrow(
      "duplicate sensor source_id: sim-temperature-1",
    );
  });

  it("rejects missing zone references, invalid dimensions, and non-finite positions", () => {
    const unknownZone = copyLayout();
    unknownZone.sensors = unknownZone.sensors.map((sensor, index) =>
      index === 0 ? { ...sensor, zoneId: "not-a-zone" } : sensor,
    );
    expect(() => validateFarmLayout(unknownZone)).toThrow("references unknown zone not-a-zone");

    const invalidDimensions = copyLayout();
    invalidDimensions.site.dimensions.width = 0;
    expect(() => validateFarmLayout(invalidDimensions)).toThrow("positive dimensions");

    const invalidPosition = copyLayout();
    invalidPosition.sensors = invalidPosition.sensors.map((sensor, index) =>
      index === 0 ? { ...sensor, position: [Number.NaN, 2, 0] } : sensor,
    );
    expect(() => validateFarmLayout(invalidPosition)).toThrow("only finite coordinates");
  });

  it("rejects zones and sensors outside the configured site", () => {
    const outsideZone = copyLayout();
    outsideZone.zones = outsideZone.zones.map((zone, index) =>
      index === 0 ? { ...zone, center: [-17, -2] } : zone,
    );
    expect(() => validateFarmLayout(outsideZone)).toThrow("inside the site footprint");

    const outsideSensor = copyLayout();
    outsideSensor.sensors = outsideSensor.sensors.map((sensor, index) =>
      index === 0 ? { ...sensor, position: [-18, 2, 0] } : sensor,
    );
    expect(() => validateFarmLayout(outsideSensor)).toThrow("inside the site bounds");
  });
});
