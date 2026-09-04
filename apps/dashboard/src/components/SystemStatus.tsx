import type { TelemetryState } from "../useTelemetry";
import { StatusBadge } from "./StatusBadge";

interface StatusItemProps {
  label: string;
  detail: string;
  state:
    | "available"
    | "unavailable"
    | "last-known-available"
    | "last-known-unavailable"
    | "unknown"
    | "checking";
}

function StatusItem({ label, detail, state }: StatusItemProps) {
  const isAvailable = state === "available";
  const isUnavailable = state === "unavailable";
  const labelByState = {
    available: "Available",
    unavailable: "Unavailable",
    "last-known-available": "Last known · available",
    "last-known-unavailable": "Last known · unavailable",
    unknown: "Unknown",
    checking: "Checking",
  } as const;
  return (
    <article className="system-status__item">
      <div className="system-status__heading">
        <span className={`status-dot status-dot--${state}`} aria-hidden="true" />
        <h3>{label}</h3>
      </div>
      <p>{detail}</p>
      <StatusBadge
        tone={isAvailable ? "positive" : isUnavailable ? "negative" : "neutral"}
      >
        {labelByState[state]}
      </StatusBadge>
    </article>
  );
}

export function SystemStatus({ telemetry }: { telemetry: TelemetryState }) {
  const apiState = telemetry.livenessError
    ? "unavailable"
    : telemetry.liveness
      ? "available"
      : "checking";
  const readinessIsLastKnown = telemetry.readinessError !== null && telemetry.readiness !== null;
  const readyState = telemetry.readinessError
    ? readinessIsLastKnown
      ? telemetry.readiness?.status === "ready"
        ? "last-known-available"
        : "last-known-unavailable"
      : "unknown"
    : telemetry.readiness
      ? telemetry.readiness.status === "ready"
        ? "available"
        : "unavailable"
      : "checking";
  const dependencyState = (available: boolean | undefined) => {
    if (telemetry.readinessError) {
      if (available === undefined) {
        return "unknown" as const;
      }
      return available ? ("last-known-available" as const) : ("last-known-unavailable" as const);
    }
    if (available === undefined) {
      return "checking" as const;
    }
    return available ? ("available" as const) : ("unavailable" as const);
  };
  const databaseState = dependencyState(telemetry.readiness?.dependencies.postgresql);
  const mqttState = dependencyState(telemetry.readiness?.dependencies.mqtt);

  return (
    <section className="panel system-panel" aria-labelledby="system-status-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Infrastructure</p>
          <h2 id="system-status-title">System status</h2>
        </div>
        <p className="section-note">Health endpoints · current request state</p>
      </div>
      <div className="system-status">
        <StatusItem
          label="PigWatch API"
          detail={
            telemetry.livenessError
              ? `${telemetry.livenessError}. The current liveness request failed.`
              : "Process liveness endpoint"
          }
          state={apiState}
        />
        <StatusItem
          label="Telemetry ingestion"
          detail={
            telemetry.readinessError
              ? `${telemetry.readinessError}. ${telemetry.readiness ? "The badge is retained from the last successful request." : "No readiness state has been confirmed."}`
              : "Database + subscribed MQTT capacity"
          }
          state={readyState}
        />
        <StatusItem
          label="PostgreSQL"
          detail={
            telemetry.readinessError
              ? "Current dependency state is unverified; any badge is last-known."
              : "Observation persistence dependency"
          }
          state={databaseState}
        />
        <StatusItem
          label="MQTT subscription"
          detail={
            telemetry.readinessError
              ? "Current dependency state is unverified; any badge is last-known."
              : "Connected and SUBACK-confirmed"
          }
          state={mqttState}
        />
      </div>
    </section>
  );
}
