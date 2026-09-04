import { useEffect, useRef } from "react";

import type { StoredObservation } from "../api/types";
import { formatTimestamp, formatValue, PAYLOAD_LABELS } from "../telemetry";
import { Provenance } from "./Provenance";
import { StatusBadge } from "./StatusBadge";

function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export function ObservationDetail({
  observation,
  onClose,
}: {
  observation: StoredObservation;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const { envelope } = observation;

  useEffect(() => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || dialog.current === null) {
        return;
      }
      const focusable = [
        ...dialog.current.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ].filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.current.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.current.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || !dialog.current.contains(document.activeElement))
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    const onFocusIn = (event: FocusEvent) => {
      if (dialog.current && !dialog.current.contains(event.target as Node)) {
        closeButton.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("focusin", onFocusIn);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("focusin", onFocusIn);
      document.body.style.overflow = previousOverflow;
      if (returnFocus.current?.isConnected) {
        returnFocus.current.focus();
      }
    };
  }, [onClose]);

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        ref={dialog}
        className="detail-dialog"
        role="dialog"
        tabIndex={-1}
        aria-modal="true"
        aria-labelledby="detail-title"
        aria-describedby="detail-description"
      >
        <header className="detail-dialog__header">
          <div>
            <p className="section-kicker">Observation detail</p>
            <h2 id="detail-title">{PAYLOAD_LABELS[envelope.payload_type]}</h2>
            <p id="detail-description">Factual telemetry metadata from the PigWatch API.</p>
          </div>
          <button ref={closeButton} className="close-button" type="button" onClick={onClose}>
            <span aria-hidden="true">×</span>
            <span className="visually-hidden">Close observation detail</span>
          </button>
        </header>

        <div className="detail-dialog__reading">
          <p title={String(envelope.payload.value)}>
            {formatValue(envelope.payload.value)} <span>{envelope.payload.unit}</span>
          </p>
          <Provenance origin={envelope.source.origin} delivery={envelope.source.delivery} />
        </div>

        <div className="detail-sections">
          <section aria-labelledby="detail-identity">
            <h3 id="detail-identity">Identity & routing</h3>
            <dl className="detail-list">
              <DetailRow label="Event ID">
                <code>{envelope.event_id}</code>
              </DetailRow>
              <DetailRow label="Source ID">
                <code>{envelope.source.source_id}</code>
              </DetailRow>
              <DetailRow label="Schema version">{envelope.schema_version}</DetailRow>
              <DetailRow label="Payload type">
                <code>{envelope.payload_type}</code>
              </DetailRow>
              <DetailRow label="Machine value">
                <code>{String(envelope.payload.value)}</code> {envelope.payload.unit}
              </DetailRow>
              <DetailRow label="MQTT topic">
                <code>{observation.topic}</code>
              </DetailRow>
            </dl>
          </section>

          <section aria-labelledby="detail-timing">
            <h3 id="detail-timing">Timing</h3>
            <dl className="detail-list">
              <DetailRow label="Event time">
                <time dateTime={envelope.event_time}>{formatTimestamp(envelope.event_time)}</time>
              </DetailRow>
              <DetailRow label="Ingest time">
                <time dateTime={envelope.ingest_time}>{formatTimestamp(envelope.ingest_time)}</time>
              </DetailRow>
              <DetailRow label="Replay time">
                {envelope.replay_time === null ? (
                  <span>Not applicable — LIVE delivery</span>
                ) : (
                  <time dateTime={envelope.replay_time}>{formatTimestamp(envelope.replay_time)}</time>
                )}
              </DetailRow>
            </dl>
          </section>

          <section aria-labelledby="detail-evidence">
            <h3 id="detail-evidence">Evidence metadata</h3>
            <dl className="detail-list">
              <DetailRow label="Processing">
                <StatusBadge tone="positive">{observation.processing_outcome}</StatusBadge>
              </DetailRow>
              <DetailRow label="Late at ingestion">{observation.is_late ? "Yes" : "No"}</DetailRow>
              <DetailRow label="Clock skew detected">
                {observation.clock_skew_detected ? "Yes" : "No"}
              </DetailRow>
              <DetailRow label="Quality">
                {envelope.quality === null ? (
                  "Not provided"
                ) : (
                  <span>
                    {envelope.quality.status}
                    {envelope.quality.confidence === null
                      ? ""
                      : ` · confidence ${envelope.quality.confidence}`}
                    {envelope.quality.flags.length === 0
                      ? " · no flags"
                      : ` · ${envelope.quality.flags.join(", ")}`}
                  </span>
                )}
              </DetailRow>
              <DetailRow label="Trace">
                {envelope.trace === null ? (
                  "Not provided"
                ) : (
                  <span className="trace-values">
                    {envelope.trace.correlation_id && (
                      <code>correlation {envelope.trace.correlation_id}</code>
                    )}
                    {envelope.trace.trace_id && <code>trace {envelope.trace.trace_id}</code>}
                  </span>
                )}
              </DetailRow>
            </dl>
          </section>
        </div>
      </section>
    </div>
  );
}
