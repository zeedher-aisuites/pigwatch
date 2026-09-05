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
    <mesh position={position} castShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color="#30423b" metalness={0.2} roughness={0.62} />
    </mesh>
  );
}

function ZoneFloor({ zone }: { zone: FarmZone }) {
  return (
    <mesh position={[zone.center[0], 0.02, zone.center[1]]} receiveShadow>
      <boxGeometry args={[zone.size[0], 0.08, zone.size[1]]} />
      <meshStandardMaterial color={zone.color} metalness={0.02} roughness={0.92} />
    </mesh>
  );
}

function SensorHead({ sensor }: { sensor: SensorPlacement }) {
  const material = (
    <meshStandardMaterial
      color={sensor.color}
      emissive={sensor.color}
      emissiveIntensity={0.2}
      metalness={0.12}
      roughness={0.42}
    />
  );

  if (sensor.payloadType === "environment.temperature") {
    return (
      <mesh castShadow>
        <boxGeometry args={[1.05, 1.05, 1.05]} />
        {material}
      </mesh>
    );
  }
  if (sensor.payloadType === "environment.relative_humidity") {
    return (
      <mesh rotation={[Math.PI / 4, 0, Math.PI / 4]} castShadow>
        <dodecahedronGeometry args={[0.72, 0]} />
        {material}
      </mesh>
    );
  }
  return (
    <mesh rotation={[0, Math.PI / 4, 0]} castShadow>
      <octahedronGeometry args={[0.8, 0]} />
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
      scale={selected ? 1.2 : 1}
      onPointerDown={onPointerDown}
    >
      {selected ? (
        <mesh position={[0, 0.06, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.9, 0.095, 10, 32]} />
          <meshBasicMaterial color="#132f27" toneMapped={false} />
        </mesh>
      ) : null}
      <mesh position={[0, 0.14, 0]} castShadow>
        <cylinderGeometry args={[0.62, 0.76, 0.28, 24]} />
        <meshStandardMaterial color="#263a33" metalness={0.24} roughness={0.58} />
      </mesh>
      <mesh position={[0, headHeight / 2, 0]} castShadow>
        <cylinderGeometry args={[0.075, 0.105, headHeight, 12]} />
        <meshStandardMaterial
          color={hasTelemetry ? "#30483f" : "#58665f"}
          metalness={0.22}
          roughness={0.6}
        />
      </mesh>
      <group position={[0, headHeight, 0]}>
        <SensorHead sensor={sensor} />
        {selected ? (
          <mesh>
            <torusGeometry args={[1.12, 0.11, 10, 36]} />
            <meshBasicMaterial color="#f7fbf8" toneMapped={false} />
          </mesh>
        ) : null}
        <mesh rotation={[Math.PI / 2, 0, 0]} scale={selected ? 1.14 : 1}>
          <torusGeometry args={[0.98, selected ? 0.1 : 0.055, 10, 32]} />
          <meshBasicMaterial color={selected ? "#132f27" : sensor.color} toneMapped={false} />
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
      <Rail position={[0, 0.06, -length / 2]} size={[width + 0.3, 0.12, 0.28]} />
      <Rail position={[0, 0.06, length / 2]} size={[width + 0.3, 0.12, 0.28]} />
      <Rail position={[-width / 2, 0.06, 0]} size={[0.28, 0.12, length]} />
      <Rail position={[width / 2, 0.06, 0]} size={[0.28, 0.12, length]} />

      <mesh position={[0, -0.15, 0]} receiveShadow>
        <boxGeometry args={[width, 0.3, length]} />
        <meshStandardMaterial color="#788980" metalness={0.02} roughness={0.96} />
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
        <mesh position={[x, 3.25, z]} castShadow key={`${x}-${z}`}>
          <boxGeometry args={[0.28, 6.5, 0.28]} />
          <meshStandardMaterial color="#253831" metalness={0.24} roughness={0.58} />
        </mesh>
      ))}

      {roofFrames.flatMap((z) => [
        <mesh
          position={[-8.55, 6.58, z]}
          rotation={[0, 0, -0.16]}
          castShadow
          key={`roof-left-${z}`}
        >
          <boxGeometry args={[17.3, 0.18, 0.24]} />
          <meshStandardMaterial color="#30423b" metalness={0.2} roughness={0.62} />
        </mesh>,
        <mesh
          position={[8.55, 6.58, z]}
          rotation={[0, 0, 0.16]}
          castShadow
          key={`roof-right-${z}`}
        >
          <boxGeometry args={[17.3, 0.18, 0.24]} />
          <meshStandardMaterial color="#30423b" metalness={0.2} roughness={0.62} />
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
      <color attach="background" args={["#dce4df"]} />
      <hemisphereLight args={["#f5f7f4", "#354840", 1.35]} />
      <directionalLight
        position={[14, 24, 10]}
        intensity={2.15}
        color="#fff7e8"
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-24}
        shadow-camera-right={24}
        shadow-camera-top={20}
        shadow-camera-bottom={-20}
        shadow-camera-near={4}
        shadow-camera-far={70}
        shadow-bias={-0.0002}
      />
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
        className="farm-scene__canvas"
        aria-label={`${layout.site.label} interactive 3D presentation. Equivalent sensor information follows the scene.`}
        frameloop="demand"
        dpr={[1, 1.5]}
        shadows
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
        {layout.zones.map((zone) => (
          <span key={zone.id}>
            <i style={{ backgroundColor: zone.color }} />
            {zone.label}
          </span>
        ))}
      </div>
    </div>
  );
}
