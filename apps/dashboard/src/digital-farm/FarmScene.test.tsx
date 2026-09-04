import { render } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEVELOPMENT_FARM_LAYOUT } from "./layout";

const sceneMocks = vi.hoisted(() => ({
  camera: {
    position: { fromArray: vi.fn() },
    lookAt: vi.fn(),
  },
  renderer: { domElement: null as unknown as HTMLCanvasElement },
  invalidate: vi.fn(),
  controls: [] as Array<{
    addEventListener: ReturnType<typeof vi.fn>;
    removeEventListener: ReturnType<typeof vi.fn>;
    dispose: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    target: { x: number; y: number; z: number; fromArray: ReturnType<typeof vi.fn> };
  }>,
}));

vi.mock("@react-three/fiber", () => ({
  Canvas: () => null,
  useThree: () => ({
    camera: sceneMocks.camera,
    gl: sceneMocks.renderer,
    invalidate: sceneMocks.invalidate,
  }),
}));

vi.mock("three/examples/jsm/controls/OrbitControls.js", () => ({
  OrbitControls: class {
    enableDamping = false;
    enablePan = false;
    enableRotate = false;
    enableZoom = false;
    screenSpacePanning = true;
    minDistance = 0;
    maxDistance = 0;
    minPolarAngle = 0;
    maxPolarAngle = 0;
    target = { x: 0, y: 0, z: 0, fromArray: vi.fn() };
    addEventListener = vi.fn();
    removeEventListener = vi.fn();
    dispose = vi.fn();
    update = vi.fn();

    constructor() {
      sceneMocks.controls.push(this);
    }
  },
}));

import { CameraController, ContextLifecycle } from "./FarmScene";

beforeEach(() => {
  sceneMocks.camera.position.fromArray.mockClear();
  sceneMocks.camera.lookAt.mockClear();
  sceneMocks.invalidate.mockClear();
  sceneMocks.controls.length = 0;
  sceneMocks.renderer.domElement = document.createElement("canvas");
});

describe("FarmScene resource lifecycle", () => {
  it("detaches controls and context listeners under StrictMode mount/unmount", () => {
    const addListener = vi.spyOn(sceneMocks.renderer.domElement, "addEventListener");
    const removeListener = vi.spyOn(sceneMocks.renderer.domElement, "removeEventListener");
    const onContextLost = vi.fn();

    const rendered = render(
      <StrictMode>
        <CameraController layout={DEVELOPMENT_FARM_LAYOUT} resetToken={0} />
        <ContextLifecycle onContextLost={onContextLost} />
      </StrictMode>,
    );

    expect(sceneMocks.controls).toHaveLength(2);
    expect(sceneMocks.controls[0].dispose).toHaveBeenCalledOnce();
    expect(sceneMocks.controls[1].dispose).not.toHaveBeenCalled();
    expect(addListener).toHaveBeenCalledWith("webglcontextlost", expect.any(Function));

    const contextEvent = new Event("webglcontextlost", { cancelable: true });
    sceneMocks.renderer.domElement.dispatchEvent(contextEvent);
    expect(contextEvent.defaultPrevented).toBe(true);
    expect(onContextLost).toHaveBeenCalledOnce();

    rendered.unmount();
    expect(sceneMocks.controls[1].removeEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function),
    );
    expect(sceneMocks.controls[1].dispose).toHaveBeenCalledOnce();
    expect(removeListener).toHaveBeenCalledWith("webglcontextlost", expect.any(Function));
  });

  it("resets the canonical camera without creating another controls instance", () => {
    const { rerender } = render(
      <CameraController layout={DEVELOPMENT_FARM_LAYOUT} resetToken={0} />,
    );
    expect(sceneMocks.controls).toHaveLength(1);
    expect(sceneMocks.camera.position.fromArray).toHaveBeenLastCalledWith(
      DEVELOPMENT_FARM_LAYOUT.camera.position,
    );

    rerender(<CameraController layout={DEVELOPMENT_FARM_LAYOUT} resetToken={1} />);

    expect(sceneMocks.controls).toHaveLength(1);
    expect(sceneMocks.controls[0].target.fromArray).toHaveBeenLastCalledWith(
      DEVELOPMENT_FARM_LAYOUT.camera.target,
    );
    expect(sceneMocks.controls[0].update).toHaveBeenCalledTimes(3);
    expect(sceneMocks.invalidate).toHaveBeenCalled();
  });
});
