import type { TelemetryState } from "../useTelemetry";
import { StatusBadge } from "./StatusBadge";

interface StatusItemProps {
  label: string;
  detail: string;
  state: "available" | "unavailable" | "checking";
}

function StatusItem({ label, detail, state }: StatusItemProps) {
  return (
    <article className="system-status__item">
      <div className="system-status__heading">
        <span className={`status-dot status-dot--${state}`} aria-hidden="true" />
        <h3>{label}</h3>
      </div>
      <p>{detail}</p>
      <StatusBadge
        tone={state === "available" ? "positive" : state === "unavailable" ? "negative" : "neutral"}
      >
        {state === "available" ? "Available" : state === "unavailable" ? "Unavailable" : "Checking"}
      </StatusBadge>
    </article>
  );
}

export function SystemStatus({ telemetry }: { telemetry: TelemetryState }) {
  const apiState = telemetry.liveness
    ? "available"
    : telemetry.livenessError
      ? "unavailable"
      : "checking";
  const readyState = telemetry.readiness
    ? telemetry.readiness.status === "ready"
      ? "available"
      : "unavailable"
    : telemetry.readinessError
      ? "unavailable"
      : "checking";
  const databaseState = telemetry.readiness
    ? telemetry.readiness.dependencies.postgresql
      ? "available"
      : "unavailable"
    : "checking";
  const mqttState = telemetry.readiness
    ? telemetry.readiness.dependencies.mqtt
      ? "available"
      : "unavailable"
    : "checking";

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
          detail={telemetry.livenessError ?? "Process liveness endpoint"}
          state={apiState}
        />
        <StatusItem
          label="Telemetry ingestion"
          detail={telemetry.readinessError ?? "Database + subscribed MQTT capacity"}
          state={readyState}
        />
        <StatusItem
          label="PostgreSQL"
          detail="Observation persistence dependency"
          state={databaseState}
        />
        <StatusItem
          label="MQTT subscription"
          detail="Connected and SUBACK-confirmed"
          state={mqttState}
        />
      </div>
    </section>
  );
}
