import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { makeObservation } from "../test/fixtures";
import { HistoryChart } from "./HistoryChart";

function coordinates() {
  const chart = screen.getByRole("img");
  return [...chart.querySelectorAll("circle")].map((point) => ({
    x: Number(point.getAttribute("cx")),
    y: Number(point.getAttribute("cy")),
    label: point.querySelector("title")?.textContent ?? "",
  }));
}

function observation(value: number, eventTime: string, eventId: string) {
  return makeObservation({ value, eventTime, eventId });
}

describe("HistoryChart numeric normalization", () => {
  it.each([
    {
      name: "opposing finite extremes",
      values: [-1e308, 1e308],
    },
    {
      name: "negative extremes",
      values: [-1e308, -9e307],
    },
    {
      name: "a huge narrow range",
      values: [1e308, 1.0000000000000002e308],
    },
    {
      name: "a constant range",
      values: [1e308, 1e308],
    },
  ])("keeps SVG coordinates finite for $name", ({ values }) => {
    render(
      <HistoryChart
        observations={values.map((value, index) =>
          observation(
            value,
            `2026-09-04T12:00:0${index}Z`,
            `0199483f-0200-7000-8000-00000000000${index + 1}`,
          ),
        )}
      />,
    );

    const points = coordinates();
    expect(points).toHaveLength(2);
    for (const point of points) {
      expect(Number.isFinite(point.x)).toBe(true);
      expect(Number.isFinite(point.y)).toBe(true);
      expect(point.x).toBeGreaterThanOrEqual(28);
      expect(point.x).toBeLessThanOrEqual(692);
      expect(point.y).toBeGreaterThanOrEqual(24);
      expect(point.y).toBeLessThanOrEqual(196);
    }
    expect(points[0].x).toBeLessThan(points[1].x);
    if (values[0] === values[1]) {
      expect(points[0].y).toBe(110);
      expect(points[1].y).toBe(110);
    } else {
      expect(points[0].y).toBeGreaterThan(points[1].y);
    }
  });

  it("centers a single extreme point", () => {
    render(
      <HistoryChart
        observations={[
          observation(1e308, "2026-09-04T12:00:00Z", "0199483f-0200-7000-8000-000000000001"),
        ]}
      />,
    );

    expect(coordinates()).toEqual([
      expect.objectContaining({ x: 360, y: 110, label: expect.stringContaining("1e+308 Cel") }),
    ]);
  });

  it("preserves the existing normal-range endpoints", () => {
    render(
      <HistoryChart
        observations={[
          observation(20, "2026-09-04T12:00:00Z", "0199483f-0200-7000-8000-000000000001"),
          observation(30, "2026-09-04T12:01:00Z", "0199483f-0200-7000-8000-000000000002"),
        ]}
      />,
    );

    expect(coordinates()).toEqual([
      expect.objectContaining({ x: 28, y: 196 }),
      expect.objectContaining({ x: 692, y: 24 }),
    ]);
  });

  it("uses event ID to order equal timestamps and agrees with the latest reading", () => {
    render(
      <HistoryChart
        observations={[
          observation(22, "2026-09-04T12:00:00Z", "0199483f-0200-7000-8000-000000000002"),
          observation(21, "2026-09-04T12:00:00Z", "0199483f-0200-7000-8000-000000000001"),
        ]}
      />,
    );

    const points = coordinates();
    expect(points.map((point) => point.label.slice(0, 2))).toEqual(["21", "22"]);
    expect(screen.getByText("22 Cel")).toBeTruthy();
  });
});
