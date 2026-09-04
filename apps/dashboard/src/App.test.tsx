import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./api/client";
import type { ReadinessResponse, StoredObservation } from "./api/types";
import { App } from "./App";
import {
  dependenciesReady,
  livenessReady,
  makeObservation,
  observationResponse,
} from "./test/fixtures";

const currentTime = new Date("2026-09-04T12:01:00Z");
const fixedNow = () => new Date(currentTime);

function resolvedClient(
  observations: StoredObservation[],
  readiness: ReadinessResponse = dependenciesReady,
): ApiClient {
  return {
    getLiveness: vi.fn().mockResolvedValue(livenessReady),
    getReadiness: vi.fn().mockResolvedValue(readiness),
    getObservations: vi.fn().mockResolvedValue(observationResponse(observations)),
  };
}

function never<T>(): Promise<T> {
  return new Promise(() => undefined);
}

describe("M3 dashboard", () => {
  it("shows a purposeful loading state during the initial request", () => {
    const client: ApiClient = {
      getLiveness: () => never(),
      getReadiness: () => never(),
      getObservations: () => never(),
    };

    render(<App client={client} now={fixedNow} />);

    expect(screen.getByRole("heading", { name: "Loading persisted observations" })).toBeTruthy();
    expect(screen.getByText("Not yet")).toBeTruthy();
  });

  it("distinguishes an empty reachable API from a failure", async () => {
    render(<App client={resolvedClient([])} now={fixedNow} />);

    expect(await screen.findByRole("heading", { name: "No persisted observations yet" })).toBeTruthy();
    expect(screen.getByText("API reachable · no rows returned")).toBeTruthy();
    expect(screen.getByText(/pigwatch-simulator/)).toBeTruthy();
  });

  it("renders readiness, factual summaries, values, units, source IDs, and provenance", async () => {
    const observations = [
      makeObservation({ value: 22.4 }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        sourceId: "sim-humidity-1",
        payloadType: "environment.relative_humidity",
        value: 64.2,
        eventTime: "2026-09-04T12:00:10Z",
      }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000003",
        sourceId: "sim-nh3-1",
        payloadType: "environment.ammonia_concentration",
        value: 8.1,
        eventTime: "2026-09-04T12:00:20Z",
      }),
    ];

    render(<App client={resolvedClient(observations)} now={fixedNow} />);

    const summaryHeading = await screen.findByRole("heading", { name: "Telemetry summary" });
    const summary = summaryHeading.closest("section");
    expect(summary).toBeTruthy();
    expect(within(summary as HTMLElement).getByText("Observations loaded").parentElement?.textContent).toContain(
      "3",
    );
    expect(screen.getAllByText("sim-temperature-1").length).toBeGreaterThan(1);
    expect(screen.getAllByText("22.4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cel").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SYNTHETIC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("LIVE").length).toBeGreaterThan(0);
    expect(document.querySelector('time[datetime="2026-09-04T12:00:00Z"]')).toBeTruthy();
    expect(document.querySelector('time[datetime="2026-09-04T12:00:01Z"]')).toBeTruthy();
    expect(screen.getAllByText("Available").length).toBe(4);
  });

  it("shows an observation API error with a retry action", async () => {
    const client: ApiClient = {
      getLiveness: vi.fn().mockResolvedValue(livenessReady),
      getReadiness: vi.fn().mockResolvedValue(dependenciesReady),
      getObservations: vi.fn().mockRejectedValue(new Error("observation storage is unavailable")),
    };

    render(<App client={client} now={fixedNow} />);

    expect(
      await screen.findByRole("heading", { name: "Persisted telemetry could not be retrieved" }),
    ).toBeTruthy();
    expect(screen.getByText("observation storage is unavailable")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("shows unavailable readiness and each dependency independently", async () => {
    const readiness: ReadinessResponse = {
      status: "not_ready",
      service: "pigwatch-api",
      dependencies: { postgresql: true, mqtt: false },
    };

    render(<App client={resolvedClient([], readiness)} now={fixedNow} />);

    expect(
      await screen.findByRole("heading", { name: "Telemetry ingestion is not ready" }),
    ).toBeTruthy();
    const postgresCard = screen.getByRole("heading", { name: "PostgreSQL" }).closest("article");
    const mqttCard = screen.getByRole("heading", { name: "MQTT subscription" }).closest("article");
    expect(postgresCard?.textContent).toContain("Available");
    expect(mqttCard?.textContent).toContain("Unavailable");
  });

  it("lets current health failures override retained successful health", async () => {
    const observation = makeObservation();
    const client: ApiClient = {
      getLiveness: vi
        .fn()
        .mockResolvedValueOnce(livenessReady)
        .mockRejectedValueOnce(new Error("liveness endpoint unreachable")),
      getReadiness: vi
        .fn()
        .mockResolvedValueOnce(dependenciesReady)
        .mockRejectedValueOnce(new Error("readiness endpoint unreachable")),
      getObservations: vi
        .fn()
        .mockResolvedValueOnce(observationResponse([observation]))
        .mockRejectedValueOnce(new Error("PigWatch API could not be reached")),
    };
    const user = userEvent.setup();

    render(<App client={client} now={fixedNow} />);
    await screen.findByText("sim-temperature-1", { selector: "code" });
    await user.click(await screen.findByRole("button", { name: "Refresh data" }));

    const apiCard = screen.getByRole("heading", { name: "PigWatch API" }).closest("article");
    const ingestionCard = screen
      .getByRole("heading", { name: "Telemetry ingestion" })
      .closest("article");
    const postgresCard = screen.getByRole("heading", { name: "PostgreSQL" }).closest("article");
    const mqttCard = screen.getByRole("heading", { name: "MQTT subscription" }).closest("article");
    await waitFor(() => expect(apiCard?.textContent).toContain("Unavailable"));
    expect(apiCard?.textContent).not.toContain("Last known · available");
    expect(ingestionCard?.textContent).toContain("Last known · available");
    expect(postgresCard?.textContent).toContain("Last known · available");
    expect(mqttCard?.textContent).toContain("Last known · available");
    expect(screen.getAllByText(/Current dependency state is unverified/)).toHaveLength(2);
    expect(screen.getAllByText("sim-temperature-1").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Showing last-known telemetry" })).toBeTruthy();
  });

  it("shows observations while initial health state is unavailable or unknown", async () => {
    const client: ApiClient = {
      getLiveness: vi.fn().mockRejectedValue(new Error("liveness endpoint unreachable")),
      getReadiness: vi.fn().mockRejectedValue(new Error("readiness endpoint unreachable")),
      getObservations: vi.fn().mockResolvedValue(observationResponse([makeObservation()])),
    };

    render(<App client={client} now={fixedNow} />);

    await screen.findByText("sim-temperature-1", { selector: "code" });
    expect(
      screen.getByRole("heading", { name: "PigWatch API" }).closest("article")?.textContent,
    ).toContain("Unavailable");
    expect(
      screen.getByRole("heading", { name: "Telemetry ingestion" }).closest("article")?.textContent,
    ).toContain("Unknown");
    expect(screen.getByRole("heading", { name: "PostgreSQL" }).closest("article")?.textContent).toContain(
      "Unknown",
    );
  });

  it("keeps fresh health visible when observations fail", async () => {
    const client: ApiClient = {
      getLiveness: vi.fn().mockResolvedValue(livenessReady),
      getReadiness: vi.fn().mockResolvedValue(dependenciesReady),
      getObservations: vi.fn().mockRejectedValue(new Error("observation storage unavailable")),
    };

    render(<App client={client} now={fixedNow} />);

    await screen.findByRole("heading", { name: "Persisted telemetry could not be retrieved" });
    expect(screen.getAllByText("Available")).toHaveLength(4);
  });

  it("moves from healthy to readiness 503 semantics without losing dependency detail", async () => {
    const notReady: ReadinessResponse = {
      status: "not_ready",
      service: "pigwatch-api",
      dependencies: { postgresql: true, mqtt: false },
    };
    const client: ApiClient = {
      getLiveness: vi.fn().mockResolvedValue(livenessReady),
      getReadiness: vi.fn().mockResolvedValueOnce(dependenciesReady).mockResolvedValueOnce(notReady),
      getObservations: vi.fn().mockResolvedValue(observationResponse([])),
    };
    const user = userEvent.setup();

    render(<App client={client} now={fixedNow} />);
    await screen.findByRole("heading", { name: "No persisted observations yet" });
    await user.click(screen.getByRole("button", { name: "Refresh data" }));

    expect(
      await screen.findByRole("heading", { name: "Telemetry ingestion is not ready" }),
    ).toBeTruthy();
    expect(screen.getByRole("heading", { name: "PostgreSQL" }).closest("article")?.textContent).toContain(
      "Available",
    );
    expect(
      screen.getByRole("heading", { name: "MQTT subscription" }).closest("article")?.textContent,
    ).toContain("Unavailable");
  });

  it("replaces outage state with current health after recovery", async () => {
    const client: ApiClient = {
      getLiveness: vi
        .fn()
        .mockRejectedValueOnce(new Error("liveness endpoint unreachable"))
        .mockResolvedValueOnce(livenessReady),
      getReadiness: vi
        .fn()
        .mockRejectedValueOnce(new Error("readiness endpoint unreachable"))
        .mockResolvedValueOnce(dependenciesReady),
      getObservations: vi.fn().mockResolvedValue(observationResponse([])),
    };
    const user = userEvent.setup();

    render(<App client={client} now={fixedNow} />);
    await screen.findByRole("heading", { name: "System status is partially unavailable" });
    await user.click(screen.getByRole("button", { name: "Refresh data" }));

    await waitFor(() => expect(screen.queryByText("Unknown")).toBeNull());
    expect(screen.queryByRole("heading", { name: "System status is partially unavailable" })).toBeNull();
    expect(screen.getAllByText("Available")).toHaveLength(4);
  });

  it("labels stale telemetry as a dashboard freshness policy", async () => {
    const oldObservation = makeObservation({ eventTime: "2026-09-04T11:55:00Z" });

    render(
      <App client={resolvedClient([oldObservation])} now={fixedNow} staleAfterMs={60_000} />,
    );

    expect(
      await screen.findByRole("heading", { name: "Telemetry has not changed recently" }),
    ).toBeTruthy();
    expect(screen.getByText(/not a biological or health threshold/)).toBeTruthy();
  });

  it("filters by source, measurement, and time and resets active filters", async () => {
    const observations = [
      makeObservation({ sourceId: "source-a", eventTime: "2026-09-04T12:00:30Z" }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        sourceId: "source-b",
        payloadType: "environment.relative_humidity",
        eventTime: "2026-09-04T11:00:00Z",
      }),
    ];
    const user = userEvent.setup();

    render(<App client={resolvedClient(observations)} now={fixedNow} />);
    const table = await screen.findByRole("table");

    await user.selectOptions(screen.getByLabelText("Source"), "source-a");
    expect(within(table).getByText("source-a")).toBeTruthy();
    expect(within(table).queryByText("source-b")).toBeNull();
    expect(screen.getByText("1 active")).toBeTruthy();

    await user.selectOptions(screen.getByLabelText("Measurement"), "environment.relative_humidity");
    expect(
      await screen.findByRole("heading", { name: "No observations match these filters" }),
    ).toBeTruthy();
    expect(screen.getByText("No observations match the active filters.")).toBeTruthy();
    expect(screen.getByText("2 active")).toBeTruthy();

    await user.click(screen.getAllByRole("button", { name: "Reset filters" })[0]);
    const resetTable = await screen.findByRole("table");
    expect(within(resetTable).getByText("source-a")).toBeTruthy();
    expect(within(resetTable).getByText("source-b")).toBeTruthy();

    await user.selectOptions(screen.getByLabelText("Event time"), "15m");
    expect(within(screen.getByRole("table")).getByText("source-a")).toBeTruthy();
    expect(within(screen.getByRole("table")).queryByText("source-b")).toBeNull();
  });

  it("opens factual observation detail and represents recorded replay time", async () => {
    const recorded = makeObservation({
      delivery: "RECORDED",
      replayTime: "2026-09-04T12:00:30Z",
      quality: { status: "UNCERTAIN", confidence: 0.7, flags: ["calibration_due"] },
      trace: {
        correlation_id: "0199483f-0200-7000-8000-000000000099",
        trace_id: "7f3f55a4443f48e48a63723c23c1276f",
      },
    });
    const user = userEvent.setup();

    render(<App client={resolvedClient([recorded])} now={fixedNow} />);
    const inspect = await screen.findByRole("button", { name: /Inspect observation/ });
    await user.click(inspect);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(recorded.envelope.event_id)).toBeTruthy();
    expect(within(dialog).getByText(recorded.topic)).toBeTruthy();
    expect(within(dialog).getByText("RECORDED")).toBeTruthy();
    expect(within(dialog).getByText(/confidence 0.7/)).toBeTruthy();
    expect(dialog.querySelector('time[datetime="2026-09-04T12:00:30Z"]')).toBeTruthy();

    await user.click(within(dialog).getByRole("button", { name: "Close observation detail" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(inspect);
  });

  it("marks replay time as not applicable for live delivery and restores trigger focus", async () => {
    const live = makeObservation();
    const user = userEvent.setup();

    render(<App client={resolvedClient([live])} now={fixedNow} />);
    const inspect = await screen.findByRole("button", { name: /Inspect observation/ });
    await user.click(inspect);

    expect(screen.getByText("Not applicable — LIVE delivery")).toBeTruthy();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Close observation detail" }),
    );

    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(inspect);
  });

  it("contains modal focus and restores the trigger after a complete backdrop pointer sequence", async () => {
    const user = userEvent.setup();

    render(<App client={resolvedClient([makeObservation()])} now={fixedNow} />);
    const inspect = await screen.findByRole("button", { name: /Inspect observation/ });
    await user.click(inspect);

    const close = screen.getByRole("button", { name: "Close observation detail" });
    const background = document.querySelector(".app-shell");
    expect(background?.hasAttribute("inert")).toBe(true);
    expect(background?.getAttribute("aria-hidden")).toBe("true");
    expect(document.body.style.overflow).toBe("hidden");

    await user.tab();
    expect(document.activeElement).toBe(close);
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(close);
    inspect.focus();
    expect(document.activeElement).toBe(close);

    const backdrop = document.querySelector(".dialog-backdrop") as HTMLElement;
    await user.pointer([
      { target: backdrop },
      { keys: "[MouseLeft>]", target: backdrop },
    ]);

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(document.activeElement).toBe(close);

    await user.pointer({ keys: "[/MouseLeft]", target: backdrop });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.body.style.overflow).toBe("");
    expect(document.activeElement).toBe(inspect);
    expect(document.activeElement).not.toBe(document.body);
    expect(background?.hasAttribute("inert")).toBe(false);
    expect(background?.hasAttribute("aria-hidden")).toBe(false);

    await user.click(inspect);
    expect(screen.getByRole("dialog")).toBeTruthy();

    const reopenedBackdrop = document.querySelector(".dialog-backdrop") as HTMLElement;
    await user.pointer([
      { keys: "[TouchA>]", target: reopenedBackdrop },
      { keys: "[/TouchA]", target: reopenedBackdrop },
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(inspect);
  });

  it("renders opposing extreme values with bounded labels and finite chart coordinates", async () => {
    const observations = [
      makeObservation({ value: -1e308, eventTime: "2026-09-04T12:00:00Z" }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        value: 1e308,
        eventTime: "2026-09-04T12:00:01Z",
      }),
    ];

    render(<App client={resolvedClient(observations)} now={fixedNow} />);

    const chart = await screen.findByRole("img", { name: /values -1e\+308 to 1e\+308 Cel/ });
    expect(screen.getAllByText("1e+308").length).toBeGreaterThan(0);
    expect(screen.getByText("-1e+308–1e+308 Cel")).toBeTruthy();
    for (const point of chart.querySelectorAll("circle")) {
      expect(Number.isFinite(Number(point.getAttribute("cx")))).toBe(true);
      expect(Number.isFinite(Number(point.getAttribute("cy")))).toBe(true);
    }
    expect(document.body.textContent).not.toContain("NaN");
    expect(document.body.textContent).not.toContain("Infinity");

    fireEvent.click(screen.getAllByRole("button", { name: /Inspect observation/ })[0]);
    const dialog = screen.getByRole("dialog");
    const machineValue = within(dialog).getByText("Machine value").parentElement;
    expect(machineValue?.textContent).toContain(String(observations[0].envelope.payload.value));
    expect(machineValue?.textContent).toContain("Cel");
  });

  it("preserves last-known observations after a later refresh failure", async () => {
    const observation = makeObservation();
    const getObservations = vi
      .fn()
      .mockResolvedValueOnce(observationResponse([observation]))
      .mockRejectedValueOnce(new Error("temporary observation failure"));
    const client: ApiClient = {
      getLiveness: vi.fn().mockResolvedValue(livenessReady),
      getReadiness: vi.fn().mockResolvedValue(dependenciesReady),
      getObservations,
    };
    const user = userEvent.setup();

    render(<App client={client} now={fixedNow} />);
    await screen.findByText("sim-temperature-1", { selector: "code" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh data" })).toBeTruthy());
    await user.click(screen.getByRole("button", { name: "Refresh data" }));

    expect(await screen.findByRole("heading", { name: "Showing last-known telemetry" })).toBeTruthy();
    expect(screen.getAllByText("sim-temperature-1").length).toBeGreaterThan(0);
    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("plots only actual loaded observations with a textual equivalent", async () => {
    const observations = [
      makeObservation({ value: 21.5, eventTime: "2026-09-04T11:59:00Z" }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        value: 22.4,
        eventTime: "2026-09-04T12:00:00Z",
      }),
    ];

    render(<App client={resolvedClient(observations)} now={fixedNow} />);

    const chart = await screen.findByRole("img", { name: /2 observed points/ });
    expect(chart.querySelectorAll("circle")).toHaveLength(2);
    expect(screen.getByText("21.5–22.4 Cel")).toBeTruthy();
    expect(screen.getByText(/Exact values remain in the table/)).toBeTruthy();
    expect(document.body.textContent).not.toContain("danger zone");
  });

  it("keeps the latest card and chart aligned for equal event times", async () => {
    const observations = [
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000001",
        value: 21,
      }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        value: 22,
      }),
    ];

    render(<App client={resolvedClient(observations)} now={fixedNow} />);

    const latestSection = (await screen.findByRole("heading", { name: "Sensor readings" })).closest(
      "section",
    );
    const historySection = screen.getByRole("heading", { name: "Loaded readings over time" }).closest(
      "section",
    );
    expect(within(latestSection as HTMLElement).getByText("22")).toBeTruthy();
    expect(within(historySection as HTMLElement).getByText("22 Cel")).toBeTruthy();
  });

  it("switches the history view between loaded source and measurement series", async () => {
    const observations = [
      makeObservation({ value: 22.4 }),
      makeObservation({
        eventId: "0199483f-0200-7000-8000-000000000002",
        sourceId: "sim-humidity-1",
        payloadType: "environment.relative_humidity",
        value: 64.2,
      }),
    ];
    const user = userEvent.setup();

    render(<App client={resolvedClient(observations)} now={fixedNow} />);
    await screen.findByRole("img", { name: /Relative humidity for sim-humidity-1/ });

    await user.selectOptions(
      screen.getByLabelText("Series"),
      "sim-temperature-1\u0000environment.temperature",
    );

    expect(
      screen.getByRole("img", { name: /Air temperature for sim-temperature-1; 1 observed points/ }),
    ).toBeTruthy();
    expect(screen.getByText("22.4–22.4 Cel")).toBeTruthy();
  });
});
