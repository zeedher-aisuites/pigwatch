import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient } from "./api/client";
import type { LivenessResponse, ReadinessResponse, StoredObservation } from "./api/types";
import { errorMessage } from "./telemetry";

export interface TelemetryState {
  observations: StoredObservation[];
  observationsLoaded: boolean;
  liveness: LivenessResponse | null;
  readiness: ReadinessResponse | null;
  observationError: string | null;
  livenessError: string | null;
  readinessError: string | null;
  lastObservationRefresh: Date | null;
  refreshing: boolean;
}

const INITIAL_STATE: TelemetryState = {
  observations: [],
  observationsLoaded: false,
  liveness: null,
  readiness: null,
  observationError: null,
  livenessError: null,
  readinessError: null,
  lastObservationRefresh: null,
  refreshing: false,
};

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

export function useTelemetry(
  client: ApiClient,
  pollIntervalMs: number,
  now: () => Date,
): TelemetryState & { refresh: () => Promise<void> } {
  const [state, setState] = useState<TelemetryState>(INITIAL_STATE);
  const refreshRef = useRef<() => Promise<void>>(async () => undefined);

  useEffect(() => {
    let disposed = false;
    let timer: number | null = null;
    let controller: AbortController | null = null;
    let active: Promise<void> | null = null;

    const clearTimer = () => {
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
    };

    const schedule = () => {
      if (disposed) {
        return;
      }
      clearTimer();
      timer = window.setTimeout(() => {
        timer = null;
        if (document.hidden) {
          schedule();
          return;
        }
        void runRefresh();
      }, pollIntervalMs);
    };

    const runRefresh = (): Promise<void> => {
      clearTimer();
      if (active !== null) {
        return active;
      }
      controller = new AbortController();
      setState((current) => ({ ...current, refreshing: true }));
      active = Promise.allSettled([
        client.getLiveness(controller.signal),
        client.getReadiness(controller.signal),
        client.getObservations(controller.signal),
      ])
        .then(([liveness, readiness, observations]) => {
          if (disposed) {
            return;
          }
          setState((current) => {
            const next = { ...current, refreshing: false };
            if (liveness.status === "fulfilled") {
              next.liveness = liveness.value;
              next.livenessError = null;
            } else if (!isAbortError(liveness.reason)) {
              next.livenessError = errorMessage(liveness.reason);
            }
            if (readiness.status === "fulfilled") {
              next.readiness = readiness.value;
              next.readinessError = null;
            } else if (!isAbortError(readiness.reason)) {
              next.readinessError = errorMessage(readiness.reason);
            }
            if (observations.status === "fulfilled") {
              next.observations = observations.value.items;
              next.observationsLoaded = true;
              next.observationError = null;
              next.lastObservationRefresh = now();
            } else if (!isAbortError(observations.reason)) {
              next.observationsLoaded = true;
              next.observationError = errorMessage(observations.reason);
            }
            return next;
          });
        })
        .finally(() => {
          controller = null;
          active = null;
          if (!disposed) {
            schedule();
          }
        });
      return active;
    };

    const onVisibilityChange = () => {
      if (!document.hidden) {
        clearTimer();
        void runRefresh();
      }
    };

    refreshRef.current = runRefresh;
    document.addEventListener("visibilitychange", onVisibilityChange);
    void runRefresh();

    return () => {
      disposed = true;
      clearTimer();
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      refreshRef.current = async () => undefined;
    };
  }, [client, now, pollIntervalMs]);

  const refresh = useCallback(() => refreshRef.current(), []);
  return { ...state, refresh };
}
