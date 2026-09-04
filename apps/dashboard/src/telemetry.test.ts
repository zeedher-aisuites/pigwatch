import { describe, expect, it } from "vitest";

import { makeObservation } from "./test/fixtures";
import {
  compareObservationsAscending,
  compareObservationsDescending,
  formatValue,
  latestObservations,
} from "./telemetry";

describe("telemetry ordering and presentation", () => {
  it("breaks equal event-time ties by event ID in both directions", () => {
    const lowerId = makeObservation({
      eventId: "0199483f-0200-7000-8000-000000000001",
      value: 21,
    });
    const higherId = makeObservation({
      eventId: "0199483f-0200-7000-8000-000000000002",
      value: 22,
    });

    expect([higherId, lowerId].sort(compareObservationsAscending)).toEqual([lowerId, higherId]);
    expect([lowerId, higherId].sort(compareObservationsDescending)).toEqual([higherId, lowerId]);
    expect(latestObservations([lowerId, higherId])).toEqual([higherId]);
  });

  it("uses bounded scientific notation for extreme finite values without changing normal output", () => {
    expect(formatValue(22.4567)).toBe("22.457");
    expect(formatValue(1e308)).toBe("1e+308");
    expect(formatValue(-9.87e307)).toBe("-9.87e+307");
    expect(formatValue(1e-308)).toBe("1e-308");
    expect(formatValue(1e308).length).toBeLessThan(24);
  });
});
