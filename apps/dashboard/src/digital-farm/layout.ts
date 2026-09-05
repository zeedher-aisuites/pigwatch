import type { PayloadType } from "../api/types";
import type { FarmLayout, Vector2Tuple, Vector3Tuple } from "./types";

const SUPPORTED_PAYLOAD_TYPES = new Set<PayloadType>([
  "environment.temperature",
  "environment.relative_humidity",
  "environment.ammonia_concentration",
]);

function requireNonEmpty(value: string, label: string): void {
  if (value.trim() === "") {
    throw new Error(`${label} must be a non-empty string`);
  }
}

function requireFinite(values: readonly number[], label: string): void {
  if (values.some((value) => !Number.isFinite(value))) {
    throw new Error(`${label} must contain only finite coordinates`);
  }
}

function requirePositive(values: readonly number[], label: string): void {
  requireFinite(values, label);
  if (values.some((value) => value <= 0)) {
    throw new Error(`${label} must contain only positive dimensions`);
  }
}

function within(value: number, extent: number): boolean {
  return value >= -extent / 2 && value <= extent / 2;
}

export function validateFarmLayout(layout: FarmLayout): FarmLayout {
  requireNonEmpty(layout.site.id, "site.id");
  requireNonEmpty(layout.site.label, "site.label");
  const { width, length, height } = layout.site.dimensions;
  requirePositive([width, length, height], "site.dimensions");

  const zoneIds = new Set<string>();
  for (const zone of layout.zones) {
    requireNonEmpty(zone.id, "zone.id");
    requireNonEmpty(zone.label, `zone ${zone.id}.label`);
    if (zoneIds.has(zone.id)) {
      throw new Error(`duplicate zone id: ${zone.id}`);
    }
    zoneIds.add(zone.id);
    requireFinite(zone.center, `zone ${zone.id}.center`);
    requirePositive(zone.size, `zone ${zone.id}.size`);
    const [centerX, centerZ] = zone.center;
    const [zoneWidth, zoneLength] = zone.size;
    if (
      !within(centerX - zoneWidth / 2, width) ||
      !within(centerX + zoneWidth / 2, width) ||
      !within(centerZ - zoneLength / 2, length) ||
      !within(centerZ + zoneLength / 2, length)
    ) {
      throw new Error(`zone ${zone.id} must remain inside the site footprint`);
    }
  }

  const sourceIds = new Set<string>();
  for (const sensor of layout.sensors) {
    requireNonEmpty(sensor.sourceId, "sensor.sourceId");
    requireNonEmpty(sensor.label, `sensor ${sensor.sourceId}.label`);
    requireNonEmpty(sensor.markerCode, `sensor ${sensor.sourceId}.markerCode`);
    if (sourceIds.has(sensor.sourceId)) {
      throw new Error(`duplicate sensor source_id: ${sensor.sourceId}`);
    }
    sourceIds.add(sensor.sourceId);
    if (!zoneIds.has(sensor.zoneId)) {
      throw new Error(`sensor ${sensor.sourceId} references unknown zone ${sensor.zoneId}`);
    }
    if (!SUPPORTED_PAYLOAD_TYPES.has(sensor.payloadType)) {
      throw new Error(`sensor ${sensor.sourceId} uses an unsupported payload type`);
    }
    requireFinite(sensor.position, `sensor ${sensor.sourceId}.position`);
    const [x, y, z] = sensor.position;
    if (!within(x, width) || y < 0 || y > height || !within(z, length)) {
      throw new Error(`sensor ${sensor.sourceId} must remain inside the site bounds`);
    }
  }

  requireFinite(layout.camera.position, "camera.position");
  requireFinite(layout.camera.target, "camera.target");
  requirePositive(
    [
      layout.camera.fieldOfView,
      layout.camera.near,
      layout.camera.far,
      layout.camera.minimumDistance,
      layout.camera.maximumDistance,
      layout.camera.minimumPolarAngle,
      layout.camera.maximumPolarAngle,
    ],
    "camera constraints",
  );
  if (
    layout.camera.near >= layout.camera.far ||
    layout.camera.minimumDistance >= layout.camera.maximumDistance ||
    layout.camera.minimumPolarAngle >= layout.camera.maximumPolarAngle
  ) {
    throw new Error("camera ranges must increase from minimum to maximum");
  }

  return layout;
}

const position = (x: number, y: number, z: number): Vector3Tuple => [x, y, z];
const footprint = (x: number, z: number): Vector2Tuple => [x, z];

export const DEVELOPMENT_FARM_LAYOUT = validateFarmLayout({
  site: {
    id: "development-farm",
    label: "Development Farm",
    dimensions: { width: 34, length: 24, height: 8 },
  },
  zones: [
    {
      id: "pen-a",
      label: "Pen A",
      center: footprint(-8, -2),
      size: footprint(14, 11),
      color: "#9fb7a8",
    },
    {
      id: "pen-b",
      label: "Pen B",
      center: footprint(8, -2),
      size: footprint(14, 11),
      color: "#8fadb1",
    },
    {
      id: "service-aisle",
      label: "Service Aisle",
      center: footprint(0, 7),
      size: footprint(30, 4),
      color: "#b7aa8c",
    },
  ],
  sensors: [
    {
      sourceId: "sim-temperature-1",
      label: "Pen A temperature",
      markerCode: "T-01",
      zoneId: "pen-a",
      payloadType: "environment.temperature",
      position: position(-8, 2.2, -2),
      color: "#c96d32",
    },
    {
      sourceId: "sim-humidity-1",
      label: "Pen B humidity",
      markerCode: "RH-01",
      zoneId: "pen-b",
      payloadType: "environment.relative_humidity",
      position: position(8, 2.2, -2),
      color: "#277c8b",
    },
    {
      sourceId: "sim-nh3-1",
      label: "Service aisle NH3",
      markerCode: "N-01",
      zoneId: "service-aisle",
      payloadType: "environment.ammonia_concentration",
      position: position(0, 2.2, 7),
      color: "#6f5aa3",
    },
  ],
  camera: {
    position: position(28, 23, 32),
    target: position(0, 1, 0),
    fieldOfView: 38,
    near: 0.1,
    far: 150,
    minimumDistance: 18,
    maximumDistance: 58,
    minimumPolarAngle: 0.35,
    maximumPolarAngle: 1.45,
  },
});

export function zoneFor(layout: FarmLayout, zoneId: string) {
  const zone = layout.zones.find((candidate) => candidate.id === zoneId);
  if (zone === undefined) {
    throw new Error(`layout references unknown zone ${zoneId}`);
  }
  return zone;
}
