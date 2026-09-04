import { afterEach, describe, expect, it, vi } from "vitest";

import { makeObservation, observationResponse } from "../test/fixtures";
import { ApiRequestError, createApiClient, parseObservationList } from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PigWatch API client", () => {
  it("retrieves and validates newest bounded observations", async () => {
    const observation = makeObservation();
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(observationResponse([observation])));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createApiClient("/api", 200).getObservations();

    expect(result).toEqual(observationResponse([observation]));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/observations?limit=200&order=desc",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );
  });

  it("retrieves liveness and treats readiness 503 as dependency state", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ status: "ok", service: "pigwatch-api" }))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            status: "not_ready",
            service: "pigwatch-api",
            dependencies: { postgresql: true, mqtt: false },
          },
          503,
        ),
      );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient("/api");

    await expect(client.getLiveness()).resolves.toEqual({
      status: "ok",
      service: "pigwatch-api",
    });
    await expect(client.getReadiness()).resolves.toEqual({
      status: "not_ready",
      service: "pigwatch-api",
      dependencies: { postgresql: true, mqtt: false },
    });
  });

  it("reports HTTP failures explicitly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "observation storage is unavailable" }, 503)),
    );

    const request = createApiClient("/api").getObservations();

    await expect(request).rejects.toEqual(
      expect.objectContaining<ApiRequestError>({
        name: "ApiRequestError",
        message: "observation storage is unavailable",
        status: 503,
      }),
    );
  });

  it("rejects malformed or incoherent observation responses", async () => {
    const malformed = observationResponse([
      {
        ...makeObservation(),
        envelope: {
          ...makeObservation().envelope,
          payload: { value: Number.NaN, unit: "Cel" },
        },
      },
    ]);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(malformed)));

    await expect(createApiClient("/api").getObservations()).rejects.toThrow(
      "envelope.payload.value must be finite",
    );
  });

  it("enforces the response-size contract before parsing observation items", () => {
    const observation = makeObservation();

    expect(parseObservationList(observationResponse([]), 10)).toEqual(observationResponse([]));
    expect(parseObservationList(observationResponse([observation, observation]), 2).count).toBe(2);
    expect(parseObservationList(observationResponse(Array(500).fill(observation)), 500).count).toBe(
      500,
    );
    expect(() =>
      parseObservationList(observationResponse(Array(501).fill(observation)), 500),
    ).toThrow("observation response exceeds the absolute limit of 500 items");
    expect(() =>
      parseObservationList(observationResponse([observation, observation]), 1),
    ).toThrow("observation response exceeds the requested limit of 1 items");
    expect(() =>
      parseObservationList({ items: [observation], count: 2 }, 2),
    ).toThrow("observation response count does not match its items");
  });

  it.each([
    "2026-09-04T12:00:00Z",
    "2026-09-04T12:00:00.123456Z",
    "2026-09-04T12:00:00+05:30",
    "2026-09-04T12:00:00-06:00",
  ])("accepts timezone-aware RFC 3339 timestamps: %s", (timestamp) => {
    const observation = makeObservation({
      delivery: "RECORDED",
      eventTime: timestamp,
      ingestTime: timestamp,
      replayTime: timestamp,
    });

    expect(parseObservationList(observationResponse([observation]))).toEqual(
      observationResponse([observation]),
    );
  });

  it.each([
    "2026-09-04",
    "2026-09-04T12:00:00",
    "2026-02-30T12:00:00Z",
    "2026-09-04T12:00:00+24:00",
    "Sep 4 2026 12:00:00 GMT",
  ])("rejects non-RFC-3339 or invalid timestamps: %s", (timestamp) => {
    expect(() =>
      parseObservationList(observationResponse([makeObservation({ eventTime: timestamp })])),
    ).toThrow(/timezone-aware RFC 3339 timestamp/);
  });

  it("validates ingest and replay timestamps with the same strict rules", () => {
    expect(() =>
      parseObservationList(
        observationResponse([makeObservation({ ingestTime: "2026-09-04T12:00:01" })]),
      ),
    ).toThrow("envelope.ingest_time must be a timezone-aware RFC 3339 timestamp");
    expect(() =>
      parseObservationList(
        observationResponse([
          makeObservation({ delivery: "RECORDED", replayTime: "2026-09-04 12:00:30Z" }),
        ]),
      ),
    ).toThrow("envelope.replay_time must be a timezone-aware RFC 3339 timestamp");
  });

  it("reports malformed JSON and network failures distinctly", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response("not-json", { status: 200 }))
        .mockRejectedValueOnce(new TypeError("network down")),
    );
    const client = createApiClient("/api");

    await expect(client.getObservations()).rejects.toThrow("PigWatch API returned invalid JSON");
    await expect(client.getObservations()).rejects.toThrow("PigWatch API could not be reached");
  });

  it("propagates request cancellation", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, options: RequestInit) => {
        return new Promise<Response>((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => {
            reject(new DOMException("The request was aborted", "AbortError"));
          });
        });
      }),
    );
    const controller = new AbortController();
    const request = createApiClient("/api").getLiveness(controller.signal);

    controller.abort();

    await expect(request).rejects.toEqual(expect.objectContaining({ name: "AbortError" }));
  });
});
