import type { StoredObservation } from "../api/types";
import {
  formatRelativeTime,
  formatTimestamp,
  formatValue,
  latestObservations,
  PAYLOAD_LABELS,
} from "../telemetry";
import { Provenance } from "./Provenance";

function measurementCode(payloadType: StoredObservation["envelope"]["payload_type"]): string {
  if (payloadType === "environment.temperature") {
    return "TEMP";
  }
  if (payloadType === "environment.relative_humidity") {
    return "RH";
  }
  return "NH3";
}

export function LatestReadings({
  observations,
  now,
}: {
  observations: StoredObservation[];
  now: Date;
}) {
  const readings = latestObservations(observations);

  return (
    <section aria-labelledby="latest-readings-title">
      <div className="section-heading section-heading--outside">
        <div>
          <p className="section-kicker">Latest by source</p>
          <h2 id="latest-readings-title">Sensor readings</h2>
        </div>
        <p className="section-note">Observed values · no health interpretation</p>
      </div>
      <div className="reading-grid">
        {readings.map((observation) => {
          const { envelope } = observation;
          return (
            <article className="reading-card" key={`${envelope.source.source_id}-${envelope.payload_type}`}>
              <div className="reading-card__topline">
                <span className="measurement-code">{measurementCode(envelope.payload_type)}</span>
                <span title={envelope.event_time}>
                  {formatRelativeTime(envelope.event_time, now)}
                </span>
              </div>
              <h3>{PAYLOAD_LABELS[envelope.payload_type]}</h3>
              <p className="reading-card__value" title={String(envelope.payload.value)}>
                {formatValue(envelope.payload.value)} <span>{envelope.payload.unit}</span>
              </p>
              <dl className="reading-card__metadata">
                <div>
                  <dt>Source</dt>
                  <dd>{envelope.source.source_id}</dd>
                </div>
                <div>
                  <dt>Event</dt>
                  <dd>
                    <time dateTime={envelope.event_time}>{formatTimestamp(envelope.event_time)}</time>
                  </dd>
                </div>
                <div>
                  <dt>Ingested</dt>
                  <dd>
                    <time dateTime={envelope.ingest_time}>{formatTimestamp(envelope.ingest_time)}</time>
                  </dd>
                </div>
              </dl>
              <Provenance origin={envelope.source.origin} delivery={envelope.source.delivery} />
            </article>
          );
        })}
      </div>
    </section>
  );
}
