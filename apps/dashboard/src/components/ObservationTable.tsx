import type { StoredObservation } from "../api/types";
import { formatTimestamp, formatValue, PAYLOAD_LABELS } from "../telemetry";
import { Provenance } from "./Provenance";

export function ObservationTable({
  observations,
  totalLoaded,
  onSelect,
}: {
  observations: StoredObservation[];
  totalLoaded: number;
  onSelect: (observation: StoredObservation) => void;
}) {
  return (
    <section className="panel observations-panel" aria-labelledby="observations-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Evidence log</p>
          <h2 id="observations-title">Observations</h2>
        </div>
        <p className="section-note">
          Showing {observations.length} of {totalLoaded} loaded
        </p>
      </div>
      <div className="table-scroll" tabIndex={0} aria-label="Scrollable observation table">
        <table>
          <thead>
            <tr>
              <th scope="col">Event time</th>
              <th scope="col">Source ID</th>
              <th scope="col">Measurement</th>
              <th scope="col" className="numeric-cell">
                Value
              </th>
              <th scope="col">Provenance</th>
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {observations.map((observation) => {
              const { envelope } = observation;
              return (
                <tr key={envelope.event_id}>
                  <td className="timestamp-cell">
                    <time dateTime={envelope.event_time}>{formatTimestamp(envelope.event_time)}</time>
                  </td>
                  <td>
                    <code>{envelope.source.source_id}</code>
                  </td>
                  <td>
                    <span className="measurement-name">{PAYLOAD_LABELS[envelope.payload_type]}</span>
                    <small>{envelope.payload_type}</small>
                  </td>
                  <td
                    className="numeric-cell observation-value"
                    title={String(envelope.payload.value)}
                  >
                    {formatValue(envelope.payload.value)} <small>{envelope.payload.unit}</small>
                  </td>
                  <td>
                    <Provenance
                      origin={envelope.source.origin}
                      delivery={envelope.source.delivery}
                      compact
                    />
                  </td>
                  <td className="action-cell">
                    <button
                      className="inspect-button"
                      type="button"
                      onClick={() => onSelect(observation)}
                      aria-label={`Inspect observation ${envelope.event_id}`}
                    >
                      Inspect <span aria-hidden="true">↗</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
