import { StrictMode } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiClient } from "./api/client";
import {
  dependenciesReady,
  livenessReady,
  makeObservation,
  observationResponse,
} from "./test/fixtures";
import { useTelemetry } from "./useTelemetry";

const fixedNow = () => new Date("2026-09-04T12:01:00Z");

function Probe({ client, interval = 1_000 }: { client: ApiClient; interval?: number }) {
  const telemetry = useTelemetry(client, interval, fixedNow);
  return (
    <div>
      <span data-testid="calls-state">
        {telemetry.observationsLoaded ? telemetry.observations.length : "loading"}
      </span>
      <button type="button" onClick={() => void telemetry.refresh()}>
        Manual
      </button>
    </div>
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function clientWith(getObservations: ApiClient["getObservations"]): ApiClient {
  return {
    getLiveness: vi.fn().mockResolvedValue(livenessReady),
    getReadiness: vi.fn().mockResolvedValue(dependenciesReady),
    getObservations,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "hidden", { configurable: true, value: false });
});

describe("useTelemetry polling", () => {
  it("polls after the configured completion-based cadence", async () => {
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockResolvedValue(observationResponse([makeObservation()]));

    render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);

    expect(getObservations).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("calls-state").textContent).toBe("1");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });

    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("does not overlap a slow request and schedules only after it settles", async () => {
    const first = deferred<ReturnType<typeof observationResponse>>();
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue(observationResponse([]));

    render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(getObservations).toHaveBeenCalledTimes(1);

    await act(async () => {
      first.resolve(observationResponse([makeObservation()]));
      await first.promise;
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(getObservations).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("coalesces manual refreshes into an active automatic request", async () => {
    const first = deferred<ReturnType<typeof observationResponse>>();
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue(observationResponse([]));

    render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Manual" }));
    expect(getObservations).toHaveBeenCalledTimes(1);

    await act(async () => {
      first.resolve(observationResponse([]));
      await first.promise;
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("keeps the completion-based cadence after a failed request", async () => {
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockRejectedValue(new Error("temporary failure"));

    render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(getObservations).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("runs only one persistent polling loop under StrictMode", async () => {
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockResolvedValue(observationResponse([]));

    render(
      <StrictMode>
        <Probe client={clientWith(getObservations)} />
      </StrictMode>,
    );
    await act(async () => undefined);
    expect(getObservations).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(getObservations).toHaveBeenCalledTimes(3);
    expect(vi.getTimerCount()).toBe(1);
  });

  it("ignores a response from a disposed client lifecycle", async () => {
    const oldRequest = deferred<ReturnType<typeof observationResponse>>();
    const oldClient = clientWith(vi.fn().mockReturnValue(oldRequest.promise));
    const newClient = clientWith(
      vi.fn().mockResolvedValue(observationResponse([makeObservation(), makeObservation()])),
    );
    const view = render(<Probe client={oldClient} />);
    await act(async () => undefined);

    view.rerender(<Probe client={newClient} />);
    await act(async () => undefined);
    expect(screen.getByTestId("calls-state").textContent).toBe("2");

    await act(async () => {
      oldRequest.resolve(observationResponse([makeObservation()]));
      await oldRequest.promise;
    });
    expect(screen.getByTestId("calls-state").textContent).toBe("2");
  });

  it("skips background polls and refreshes when the page becomes visible", async () => {
    const getObservations = vi
      .fn<ApiClient["getObservations"]>()
      .mockResolvedValue(observationResponse([]));
    Object.defineProperty(document, "hidden", { configurable: true, value: true });

    render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(getObservations).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(getObservations).toHaveBeenCalledTimes(2);
  });

  it("aborts the active request and clears timers on unmount", async () => {
    let requestSignal: AbortSignal | undefined;
    const getObservations = vi.fn<ApiClient["getObservations"]>((signal) => {
      requestSignal = signal;
      return new Promise(() => undefined);
    });
    const view = render(<Probe client={clientWith(getObservations)} />);
    await act(async () => undefined);

    view.unmount();

    expect(requestSignal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});
