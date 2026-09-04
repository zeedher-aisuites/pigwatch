import type { StoredObservation } from "../api/types";
import { formatRelativeTime, formatTimestamp, newestEventTime } from "../telemetry";

export function Summary({ observations, now }: { observations: StoredObservation[]; now: Date }) {
  const newest = newestEventTime(observations);
  const sources = new Set(
    observations.map((observation) => observation.envelope.source.source_id),
  ).size;

  return (
    <section aria-labelledby="telemetry-summary-title">
      <div className="section-heading section-heading--outside">
        <div>
          <p className="section-kicker">Evidence window</p>
          <h2 id="telemetry-summary-title">Telemetry summary</h2>
        </div>
        <p className="section-note">Newest bounded API result</p>
      </div>
      <div className="summary-grid">
        <article className="summary-card">
          <p>Observations loaded</p>
          <strong>{observations.length}</strong>
          <span>Accepted evidence rows</span>
        </article>
        <article className="summary-card">
          <p>Distinct sources</p>
          <strong>{sources}</strong>
          <span>Represented in this window</span>
        </article>
        <article className="summary-card summary-card--wide">
          <p>Most recent event</p>
          <strong className="summary-card__time">
            {newest === null ? "No event time" : formatRelativeTime(newest, now)}
          </strong>
          <span>{newest === null ? "No observations loaded" : formatTimestamp(newest)}</span>
        </article>
      </div>
    </section>
  );
}
