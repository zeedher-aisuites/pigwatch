import { Canvas, type ThreeEvent, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { MathUtils, Vector3 } from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { FarmLayout, FarmZone, SensorPlacement } from "./types";

export interface FarmSceneProps {
  layout: FarmLayout;
  selectedSourceId: string;
  availableSourceIds: ReadonlySet<string>;
  onSelectSource: (sourceId: string) => void;
  onContextLost: () => void;
  resetToken: number;
}

export function CameraController({ layout, resetToken }: { layout: FarmLayout; resetToken: number }) {
  const { camera, gl, invalidate } = useThree();
  const controlsRef = useRef<OrbitControls | null>(null);

  useEffect(() => {
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = false;
    controls.enablePan = true;
    controls.enableRotate = true;
    controls.enableZoom = true;
    controls.screenSpacePanning = false;
    controls.minDistance = layout.camera.minimumDistance;
    controls.maxDistance = layout.camera.maximumDistance;
    controls.minPolarAngle = layout.camera.minimumPolarAngle;
    controls.maxPolarAngle = layout.camera.maximumPolarAngle;
    controls.target.fromArray(layout.camera.target);
    controls.update();

    const halfWidth = layout.site.dimensions.width / 2 + 2;
    const halfLength = layout.site.dimensions.length / 2 + 2;
    const onChange = () => {
      controls.target.x = MathUtils.clamp(controls.target.x, -halfWidth, halfWidth);
      controls.target.y = MathUtils.clamp(controls.target.y, 0, layout.site.dimensions.height);
      controls.target.z = MathUtils.clamp(controls.target.z, -halfLength, halfLength);
      invalidate();
    };

    controls.addEventListener("change", onChange);
    controlsRef.current = controls;
    invalidate();
    return () => {
      controls.removeEventListener("change", onChange);
      controls.dispose();
      controlsRef.current = null;
    };
  }, [camera, gl.domElement, invalidate, layout]);

  useEffect(() => {
    camera.position.fromArray(layout.camera.position);
    camera.lookAt(new Vector3(...layout.camera.target));
    const controls = controlsRef.current;
    if (controls !== null) {
      controls.target.fromArray(layout.camera.target);
      controls.update();
    }
    invalidate();
  }, [camera, invalidate, layout, resetToken]);

  return null;
}

export function ContextLifecycle({ onContextLost }: { onContextLost: () => void }) {
  const { gl } = useThree();

  useEffect(() => {
    const canvas = gl.domElement;
    const handleContextLost = (event: Event) => {
      event.preventDefault();
      onContextLost();
    };
    canvas.addEventListener("webglcontextlost", handleContextLost);
    return () => canvas.removeEventListener("webglcontextlost", handleContextLost);
  }, [gl.domElement, onContextLost]);

  return null;
}

function Rail({
  position,
  size,
}: {
  position: readonly [number, number, number];
  size: readonly [number, number, number];
}) {
  return (
    <mesh position={position}>
      <boxGeometry args={size} />
      <meshBasicMaterial color="#52615a" toneMapped={false} />
    </mesh>
  );
}

function ZoneFloor({ zone }: { zone: FarmZone }) {
  return (
    <mesh position={[zone.center[0], 0.06, zone.center[1]]} receiveShadow>
      <boxGeometry args={[zone.size[0], 0.08, zone.size[1]]} />
      <meshBasicMaterial color={zone.color} toneMapped={false} />
    </mesh>
  );
}

function SensorHead({ sensor }: { sensor: SensorPlacement }) {
  const material = (
    <meshBasicMaterial color={sensor.color} toneMapped={false} />
  );

  if (sensor.payloadType === "environment.temperature") {
    return (
      <mesh>
        <boxGeometry args={[0.8, 0.8, 0.8]} />
        {material}
      </mesh>
    );
  }
  if (sensor.payloadType === "environment.relative_humidity") {
    return (
      <mesh rotation={[Math.PI / 4, 0, Math.PI / 4]}>
        <dodecahedronGeometry args={[0.55, 0]} />
        {material}
      </mesh>
    );
  }
  return (
    <mesh rotation={[0, Math.PI / 4, 0]}>
      <octahedronGeometry args={[0.62, 0]} />
      {material}
    </mesh>
  );
}

function SensorMarker({
  sensor,
  selected,
  hasTelemetry,
  onSelect,
}: {
  sensor: SensorPlacement;
  selected: boolean;
  hasTelemetry: boolean;
  onSelect: (sourceId: string) => void;
}) {
  const onPointerDown = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    onSelect(sensor.sourceId);
  };
  const headHeight = sensor.position[1];

  return (
    <group
      position={[sensor.position[0], 0, sensor.position[2]]}
      scale={selected ? 1.14 : 1}
      onPointerDown={onPointerDown}
    >
      <mesh position={[0, 0.12, 0]}>
        <cylinderGeometry args={[0.5, 0.62, 0.22, 20]} />
        <meshBasicMaterial color="#394841" toneMapped={false} />
      </mesh>
      <mesh position={[0, headHeight / 2, 0]}>
        <cylinderGeometry args={[0.055, 0.08, headHeight, 10]} />
        <meshBasicMaterial color="#52615a" toneMapped={false} />
      </mesh>
      <group position={[0, headHeight, 0]}>
        <SensorHead sensor={sensor} />
        <mesh rotation={[Math.PI / 2, 0, 0]} scale={selected ? 1.25 : 1}>
          <torusGeometry args={[0.82, selected ? 0.07 : 0.035, 8, 28]} />
          <meshBasicMaterial
            color={selected ? "#ffffff" : sensor.color}
            transparent
            opacity={hasTelemetry ? 0.9 : 0.42}
          />
        </mesh>
      </group>
    </group>
  );
}

function FarmStructure({ layout }: { layout: FarmLayout }) {
  const { width, length } = layout.site.dimensions;
  const postX = width / 2 - 1;
  const postZ = length / 2 - 1;
  const posts = [
    [-postX, -postZ],
    [postX, -postZ],
    [-postX, postZ],
    [postX, postZ],
    [0, -postZ],
    [0, postZ],
  ] as const;
  const roofFrames = [-10, 0, 10] as const;

  return (
    <>
      <mesh position={[0, -0.38, 0]} receiveShadow>
        <boxGeometry args={[width + 7, 0.5, length + 7]} />
        <meshBasicMaterial color="#718077" toneMapped={false} />
      </mesh>
      <mesh position={[0, -0.08, 0]} receiveShadow>
        <boxGeometry args={[width, 0.35, length]} />
        <meshBasicMaterial color="#7e8b84" toneMapped={false} />
      </mesh>

      {layout.zones.map((zone) => (
        <ZoneFloor zone={zone} key={zone.id} />
      ))}

      <Rail position={[0, 0.55, -7.45]} size={[30.2, 1, 0.12]} />
      <Rail position={[0, 0.55, 3.45]} size={[30.2, 1, 0.12]} />
      <Rail position={[-15.05, 0.55, -2]} size={[0.12, 1, 11]} />
      <Rail position={[15.05, 0.55, -2]} size={[0.12, 1, 11]} />
      <Rail position={[0, 0.55, -2]} size={[0.14, 1, 11]} />

      {posts.map(([x, z]) => (
        <mesh position={[x, 3.25, z]} key={`${x}-${z}`}>
          <boxGeometry args={[0.28, 6.5, 0.28]} />
          <meshBasicMaterial color="#435049" toneMapped={false} />
        </mesh>
      ))}

      {roofFrames.flatMap((z) => [
        <mesh position={[-8.55, 6.58, z]} rotation={[0, 0, -0.16]} key={`roof-left-${z}`}>
          <boxGeometry args={[17.3, 0.18, 0.24]} />
          <meshBasicMaterial color="#52615a" toneMapped={false} />
        </mesh>,
        <mesh position={[8.55, 6.58, z]} rotation={[0, 0, 0.16]} key={`roof-right-${z}`}>
          <boxGeometry args={[17.3, 0.18, 0.24]} />
          <meshBasicMaterial color="#52615a" toneMapped={false} />
        </mesh>,
      ])}
      <Rail position={[0, 6.72, 0]} size={[0.24, 0.24, length + 1]} />
    </>
  );
}

function FarmWorld({
  layout,
  selectedSourceId,
  availableSourceIds,
  onSelectSource,
}: Omit<FarmSceneProps, "onContextLost" | "resetToken">) {
  return (
    <>
      <color attach="background" args={["#c8d3cd"]} />
      <fog attach="fog" args={["#c8d3cd", 65, 120]} />
      <hemisphereLight args={["#edf2ee", "#47554d", 0.72]} />
      <directionalLight position={[14, 24, 10]} intensity={0.82} color="#fff4df" />
      <FarmStructure layout={layout} />
      {layout.sensors.map((sensor) => (
        <SensorMarker
          key={sensor.sourceId}
          sensor={sensor}
          selected={sensor.sourceId === selectedSourceId}
          hasTelemetry={availableSourceIds.has(sensor.sourceId)}
          onSelect={onSelectSource}
        />
      ))}
    </>
  );
}

export function FarmScene(props: FarmSceneProps) {
  const { layout } = props;
  return (
    <div className="farm-scene">
      <Canvas
        aria-label={`${layout.site.label} interactive 3D presentation. Equivalent sensor information follows the scene.`}
        frameloop="demand"
        dpr={[1, 1.5]}
        camera={{
          position: [...layout.camera.position],
          fov: layout.camera.fieldOfView,
          near: layout.camera.near,
          far: layout.camera.far,
        }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: "high-performance",
          preserveDrawingBuffer: true,
        }}
      >
        <CameraController layout={layout} resetToken={props.resetToken} />
        <ContextLifecycle onContextLost={props.onContextLost} />
        <FarmWorld
          layout={layout}
          selectedSourceId={props.selectedSourceId}
          availableSourceIds={props.availableSourceIds}
          onSelectSource={props.onSelectSource}
        />
      </Canvas>
      <div className="farm-scene__orientation" aria-hidden="true">
        <span>N</span>
        <i />
      </div>
      <div className="farm-scene__zone-key" aria-hidden="true">
        <span>Pen A</span>
        <span>Pen B</span>
        <span>Service Aisle</span>
      </div>
    </div>
  );
}
