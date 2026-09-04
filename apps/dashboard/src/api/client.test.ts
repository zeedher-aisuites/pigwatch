import { afterEach, describe, expect, it, vi } from "vitest";

import { makeObservation, observationResponse } from "../test/fixtures";
import { ApiRequestError, createApiClient } from "./client";

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
