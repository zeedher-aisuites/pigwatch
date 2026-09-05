import type { PayloadType } from "../api/types";

export type Vector3Tuple = readonly [x: number, y: number, z: number];
export type Vector2Tuple = readonly [x: number, z: number];

export interface FarmSite {
  id: string;
  label: string;
  dimensions: {
    width: number;
    length: number;
    height: number;
  };
}

export interface FarmZone {
  id: string;
  label: string;
  center: Vector2Tuple;
  size: Vector2Tuple;
  color: string;
}

export interface SensorPlacement {
  sourceId: string;
  label: string;
  markerCode: string;
  zoneId: string;
  payloadType: PayloadType;
  position: Vector3Tuple;
  color: string;
}

export interface FarmCamera {
  position: Vector3Tuple;
  target: Vector3Tuple;
  fieldOfView: number;
  near: number;
  far: number;
  minimumDistance: number;
  maximumDistance: number;
  minimumPolarAngle: number;
  maximumPolarAngle: number;
}

export interface FarmLayout {
  site: FarmSite;
  zones: readonly FarmZone[];
  sensors: readonly SensorPlacement[];
  camera: FarmCamera;
}
