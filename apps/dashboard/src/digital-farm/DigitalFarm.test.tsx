import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType } from "react";
import { describe, expect, it, vi } from "vitest";

import { makeObservation } from "../test/fixtures";
import { DigitalFarm } from "./DigitalFarm";
import type { FarmSceneProps } from "./FarmScene";

const fixedNow = new Date("2026-09-04T12:01:00Z");

function TestScene(props: FarmSceneProps) {
  return (
    <div data-testid="test-scene">
      <span>reset {props.resetToken}</span>
      <span>selected {props.selectedSourceId}</span>
      <button type="button" onClick={() => props.onSelectSource("sim-nh3-1")}>
        Select NH3 marker
      </button>
      <button type="button" onClick={props.onContextLost}>
        Lose context
      </button>
    </div>
  );
}

const defaultProps = {
  observationsLoaded: true,
  observationError: null,
  staleAfterMs: 60_000,
  now: fixedNow,
};

describe("Digital Farm", () => {
  it("keeps the complete sensor directory usable without WebGL", async () => {
    const user = userEvent.setup();
    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable={false}
        observations={[
          makeObservation(),
          makeObservation({
            eventId: "0199483f-0200-7000-8000-000000000002",
            sourceId: "sim-humidity-1",
            payloadType: "environment.relative_humidity",
          }),
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "WebGL is unavailable" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /temperature/i })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /humidity/i })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: /NH3/i })).toHaveLength(1);

    const humidity = screen.getByRole("button", { name: /Pen B humidity/ });
    await user.click(humidity);
    expect(humidity.getAttribute("aria-pressed")).toBe("true");
    const detail = screen.getByRole("heading", { name: "Pen B humidity" }).closest("aside");
    expect(detail).not.toBeNull();
    expect(within(detail as HTMLElement).getByText("64.2")).toBeTruthy();
    expect(within(detail as HTMLElement).getByText("%")).toBeTruthy();
    expect(within(detail as HTMLElement).getByText("SYNTHETIC")).toBeTruthy();
    expect(within(detail as HTMLElement).getByText("LIVE")).toBeTruthy();
  });

  it("shows loading, no-telemetry, and API-unavailable states without fabricating a value", () => {
    const { rerender } = render(
      <DigitalFarm
        {...defaultProps}
        observationsLoaded={false}
        webglAvailable={false}
        observations={[]}
      />,
    );
    expect(screen.getAllByText("WAITING FOR TELEMETRY").length).toBeGreaterThan(0);

    rerender(
      <DigitalFarm {...defaultProps} webglAvailable={false} observations={[]} />,
    );
    expect(screen.getAllByText("NO RECENT TELEMETRY").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("0 Cel");

    rerender(
      <DigitalFarm
        {...defaultProps}
        observationError="PigWatch API could not be reached"
        webglAvailable={false}
        observations={[]}
      />,
    );
    expect(screen.getByText(/The API request is unavailable/)).toBeTruthy();
  });

  it("synchronizes marker and textual selection through one source ID", async () => {
    const user = userEvent.setup();
    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable
        SceneComponent={TestScene}
        observations={[
          makeObservation({
            eventId: "0199483f-0200-7000-8000-000000000003",
            sourceId: "sim-nh3-1",
            payloadType: "environment.ammonia_concentration",
            value: 8.4,
          }),
        ]}
      />,
    );

    expect(screen.getByText("selected sim-temperature-1")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Select NH3 marker" }));
    expect(screen.getByText("selected sim-nh3-1")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Service aisle NH3/ }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.getByRole("heading", { name: "Service aisle NH3" })).toBeTruthy();
    expect(screen.getByText("8.4")).toBeTruthy();
    expect(screen.getAllByText("[ppm]").length).toBeGreaterThan(0);
  });

  it("signals camera reset and preserves list-only operation", async () => {
    const user = userEvent.setup();
    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable
        SceneComponent={TestScene}
        observations={[]}
      />,
    );

    expect(screen.getByText("reset 0")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Reset camera" }));
    expect(screen.getByText("reset 1")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Use list only" }));
    expect(screen.queryByTestId("test-scene")).toBeNull();
    expect(screen.getByRole("button", { name: "Show 3D view" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Placed sensors" })).toBeTruthy();
  });

  it("handles context loss and remounts the scene on retry", async () => {
    const user = userEvent.setup();
    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable
        SceneComponent={TestScene}
        observations={[]}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Lose context" }));
    expect(screen.getByRole("heading", { name: "The 3D graphics context was lost" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Try 3D again" }));
    expect(screen.getByTestId("test-scene")).toBeTruthy();
  });

  it("contains render failures and leaves factual HTML available", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const BrokenScene: ComponentType<FarmSceneProps> = () => {
      throw new Error("renderer failed");
    };

    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable
        SceneComponent={BrokenScene}
        observations={[]}
      />,
    );

    expect(screen.getByRole("heading", { name: "The 3D view could not render" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Placed sensors" })).toBeTruthy();
    expect(consoleError).toHaveBeenCalledWith(
      "Digital Farm 3D rendering failed",
      expect.any(Error),
      expect.any(String),
    );
    consoleError.mockRestore();
  });

  it("keeps unplaced evidence visible as a link back to M3", () => {
    render(
      <DigitalFarm
        {...defaultProps}
        webglAvailable={false}
        observations={[makeObservation({ sourceId: "unplaced-environment-source" })]}
      />,
    );

    expect(screen.getByText("1 loaded source(s) have no M4 placement.")).toBeTruthy();
    expect(screen.getByText(/unplaced-environment-source/)).toBeTruthy();
    expect(screen.getByText(/remain available in the Telemetry view/)).toBeTruthy();
  });
});
