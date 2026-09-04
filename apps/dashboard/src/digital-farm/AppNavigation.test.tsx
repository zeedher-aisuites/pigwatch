import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "../App";
import type { ApiClient } from "../api/client";
import {
  dependenciesReady,
  livenessReady,
  makeObservation,
  observationResponse,
} from "../test/fixtures";

describe("M3 and M4 view integration", () => {
  it("keeps the existing telemetry console accessible beside the Digital Farm", async () => {
    const client: ApiClient = {
      getLiveness: vi.fn().mockResolvedValue(livenessReady),
      getReadiness: vi.fn().mockResolvedValue(dependenciesReady),
      getObservations: vi.fn().mockResolvedValue(observationResponse([makeObservation()])),
    };
    const user = userEvent.setup();

    render(<App client={client} now={() => new Date("2026-09-04T12:01:00Z")} />);
    expect(await screen.findByRole("heading", { name: "Sensor readings" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Digital Farm" }));
    expect(screen.getByRole("heading", { name: "Every reading, grounded in place." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Development Farm" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Placed sensors" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Telemetry" }));
    expect(screen.getByRole("heading", { name: "Operational evidence, clearly in view." })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Sensor readings" })).toBeTruthy();
    expect(screen.getByText("sim-temperature-1", { selector: "code" })).toBeTruthy();
  });
});
