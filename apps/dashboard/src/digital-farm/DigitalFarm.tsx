import {
  Component,
  lazy,
  Suspense,
  useCallback,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";

import type { StoredObservation } from "../api/types";
import { Provenance } from "../components/Provenance";
import {
  formatRelativeTime,
  formatTimestamp,
  formatValue,
  PAYLOAD_LABELS,
} from "../telemetry";
import { DEVELOPMENT_FARM_LAYOUT, zoneFor } from "./layout";
import { mapFarmTelemetry, type SpatialReading } from "./telemetryMapping";
import type { FarmSceneProps } from "./FarmScene";
import { supportsWebGL } from "./webgl";

const LazyFarmScene = lazy(async () => {
  const module = await import("./FarmScene");
  return { default: module.FarmScene };
});

interface SceneBoundaryProps {
  children: ReactNode;
  fallback: ReactNode;
}

interface SceneBoundaryState {
  failed: boolean;
}

class SceneBoundary extends Component<SceneBoundaryProps, SceneBoundaryState> {
  state: SceneBoundaryState = { failed: false };

  static getDerivedStateFromError(): SceneBoundaryState {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Digital Farm 3D rendering failed", error, info.componentStack);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

function measurementCode(reading: SpatialReading): string {
  if (reading.placement.payloadType === "environment.temperature") {
    return "TEMP";
  }
  if (reading.placement.payloadType === "environment.relative_humidity") {
    return "RH";
  }
  return "NH3";
}

function SceneUnavailable({
  title,
  children,
  onRetry,
}: {
  title: string;
  children: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div className="farm-scene-state" role="status">
      <span className="farm-scene-state__mark" aria-hidden="true">
        2D
      </span>
      <div>
        <p className="section-kicker">Non-3D mode</p>
        <h3>{title}</h3>
        <p>{children}</p>
        {onRetry !== undefined && (
          <button className="button button--quiet" type="button" onClick={onRetry}>
            Try 3D again
          </button>
        )}
      </div>
    </div>
  );
}

function SelectedSensor({
  reading,
  observationsLoaded,
  observationError,
  staleAfterMs,
  now,
}: {
  reading: SpatialReading;
  observationsLoaded: boolean;
  observationError: string | null;
  staleAfterMs: number;
  now: Date;
}) {
  const zone = zoneFor(DEVELOPMENT_FARM_LAYOUT, reading.placement.zoneId);
  const observation = reading.observation;

  return (
    <aside className="farm-detail panel" aria-labelledby="selected-sensor-title">
      <div className="farm-detail__header">
        <span
          className="sensor-symbol"
          style={{ "--sensor-color": reading.placement.color } as React.CSSProperties}
          aria-hidden="true"
        >
          {reading.placement.markerCode}
        </span>
        <div>
          <p className="section-kicker">Selected placement</p>
          <h2 id="selected-sensor-title">{reading.placement.label}</h2>
        </div>
      </div>
      <dl className="farm-detail__identity">
        <div>
          <dt>Zone</dt>
          <dd>{zone.label}</dd>
        </div>
        <div>
          <dt>Source ID</dt>
          <dd>
            <code>{reading.placement.sourceId}</code>
          </dd>
        </div>
        <div>
          <dt>Measurement</dt>
          <dd>{PAYLOAD_LABELS[reading.placement.payloadType]}</dd>
        </div>
        <div>
          <dt>Payload type</dt>
          <dd>
            <code>{reading.placement.payloadType}</code>
          </dd>
        </div>
      </dl>

      {!observationsLoaded ? (
        <div className="farm-reading-state" role="status" aria-busy="true">
          <strong>WAITING FOR TELEMETRY</strong>
          <span>The initial M1 API observation request is still in progress.</span>
        </div>
      ) : observation === null ? (
        <div className="farm-reading-state" role="status">
          <strong>NO RECENT TELEMETRY</strong>
          <span>
            {observationError === null
              ? "No matching observation exists in the loaded API window."
              : `The API request is unavailable: ${observationError}`}
          </span>
        </div>
      ) : (
        <div className="farm-reading">
          <p className="farm-reading__value" title={String(observation.envelope.payload.value)}>
            {formatValue(observation.envelope.payload.value)}
            <span>{observation.envelope.payload.unit}</span>
          </p>
          <p className="farm-reading__freshness">
            Last observation {formatRelativeTime(observation.envelope.event_time, now)}
            {now.getTime() - Date.parse(observation.envelope.event_time) > staleAfterMs
              ? ` · outside the ${Math.round(staleAfterMs / 1_000)}s dashboard freshness window`
              : ""}
          </p>
          <dl className="farm-reading__times">
            <div>
              <dt>Event time</dt>
              <dd>
                <time dateTime={observation.envelope.event_time}>
                  {formatTimestamp(observation.envelope.event_time)}
                </time>
              </dd>
            </div>
            <div>
              <dt>Ingest time</dt>
              <dd>
                <time dateTime={observation.envelope.ingest_time}>
                  {formatTimestamp(observation.envelope.ingest_time)}
                </time>
              </dd>
            </div>
            <div>
              <dt>Replay time</dt>
              <dd>
                {observation.envelope.replay_time === null ? (
                  "Not applicable — LIVE delivery"
                ) : (
                  <time dateTime={observation.envelope.replay_time}>
                    {formatTimestamp(observation.envelope.replay_time)}
                  </time>
                )}
              </dd>
            </div>
          </dl>
          <Provenance
            origin={observation.envelope.source.origin}
            delivery={observation.envelope.source.delivery}
          />
        </div>
      )}
      <p className="farm-detail__guardrail">Observed evidence · no health interpretation</p>
    </aside>
  );
}

function SensorDirectory({
  readings,
  selectedSourceId,
  onSelect,
  observationsLoaded,
}: {
  readings: readonly SpatialReading[];
  selectedSourceId: string;
  onSelect: (sourceId: string) => void;
  observationsLoaded: boolean;
}) {
  return (
    <section className="farm-directory panel" aria-labelledby="farm-directory-title">
      <div className="section-heading">
        <div>
          <p className="section-kicker">Accessible spatial index</p>
          <h2 id="farm-directory-title">Placed sensors</h2>
        </div>
        <p className="section-note">Keyboard-accessible · spatial sensors only</p>
      </div>
      <div className="farm-directory__grid">
        {readings.map((reading) => {
          const selected = reading.placement.sourceId === selectedSourceId;
          const zone = zoneFor(DEVELOPMENT_FARM_LAYOUT, reading.placement.zoneId);
          return (
            <button
              className={`sensor-directory-card ${selected ? "sensor-directory-card--selected" : ""}`}
              type="button"
              key={reading.placement.sourceId}
              onClick={() => onSelect(reading.placement.sourceId)}
              aria-pressed={selected}
            >
              <span className="sensor-directory-card__topline">
                <span
                  className="sensor-directory-card__code"
                  style={{ "--sensor-color": reading.placement.color } as React.CSSProperties}
                >
                  {measurementCode(reading)} · {reading.placement.markerCode}
                </span>
                <span>{zone.label}</span>
              </span>
              <strong>{reading.placement.label}</strong>
              <code>{reading.placement.sourceId}</code>
              <span className="sensor-directory-card__reading">
                {!observationsLoaded
                  ? "WAITING FOR TELEMETRY"
                  : reading.observation === null
                    ? "NO RECENT TELEMETRY"
                    : `${formatValue(reading.observation.envelope.payload.value)} ${reading.observation.envelope.payload.unit}`}
              </span>
              {reading.observation !== null && (
                <Provenance
                  origin={reading.observation.envelope.source.origin}
                  delivery={reading.observation.envelope.source.delivery}
                  compact
                />
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}

export function DigitalFarm({
  observations,
  observationsLoaded,
  observationError,
  staleAfterMs,
  now,
  webglAvailable,
  SceneComponent = LazyFarmScene,
}: {
  observations: StoredObservation[];
  observationsLoaded: boolean;
  observationError: string | null;
  staleAfterMs: number;
  now: Date;
  webglAvailable?: boolean;
  SceneComponent?: React.ComponentType<FarmSceneProps>;
}) {
  const layout = DEVELOPMENT_FARM_LAYOUT;
  const mapping = useMemo(() => mapFarmTelemetry(layout, observations), [layout, observations]);
  const [selectedSourceId, setSelectedSourceId] = useState(layout.sensors[0].sourceId);
  const [showScene, setShowScene] = useState(true);
  const [resetToken, setResetToken] = useState(0);
  const [sceneAttempt, setSceneAttempt] = useState(0);
  const [contextLost, setContextLost] = useState(false);
  const canRender3D = useMemo(
    () => webglAvailable ?? supportsWebGL(),
    [webglAvailable],
  );
  const selectedReading = mapping.bySourceId.get(selectedSourceId) ?? mapping.readings[0];
  const availableSourceIds = useMemo(
    () =>
      new Set(
        mapping.readings
          .filter((reading) => reading.observation !== null)
          .map((reading) => reading.placement.sourceId),
      ),
    [mapping.readings],
  );
  const retryScene = useCallback(() => {
    setContextLost(false);
    setSceneAttempt((attempt) => attempt + 1);
  }, []);

  return (
    <div className="digital-farm">
      <section className="farm-overview" aria-labelledby="farm-overview-title">
        <div>
          <p className="section-kicker">Deterministic development layout</p>
          <h2 id="farm-overview-title">{layout.site.label}</h2>
          <p>
            A spatial presentation of three configured M2 environmental sources. Placement metadata
            is local to this view and remains separate from telemetry evidence.
          </p>
        </div>
        <dl className="farm-overview__facts">
          <div>
            <dt>Site</dt>
            <dd>{layout.site.id}</dd>
          </div>
          <div>
            <dt>Footprint</dt>
            <dd>
              {layout.site.dimensions.width} × {layout.site.dimensions.length} m
            </dd>
          </div>
          <div>
            <dt>Placed</dt>
            <dd>{layout.sensors.length} sensors</dd>
          </div>
        </dl>
      </section>

      {mapping.unplacedSourceIds.length > 0 && (
        <div className="farm-unplaced-notice" role="status">
          <strong>{mapping.unplacedSourceIds.length} loaded source(s) have no M4 placement.</strong>
          <span>They remain available in the Telemetry view: {mapping.unplacedSourceIds.join(", ")}.</span>
        </div>
      )}

      <div className="farm-toolbar" aria-label="Digital Farm view controls">
        <div className="farm-toolbar__instructions">
          <strong>Navigate the farm</strong>
          <span>Drag to orbit · right-drag to pan · wheel or pinch to zoom</span>
        </div>
        <div className="farm-toolbar__actions">
          {showScene && canRender3D && !contextLost && (
            <button
              className="button button--quiet"
              type="button"
              onClick={() => setResetToken((token) => token + 1)}
            >
              Reset camera
            </button>
          )}
          <button
            className="button button--quiet"
            type="button"
            onClick={() => setShowScene((visible) => !visible)}
          >
            {showScene ? "Use list only" : "Show 3D view"}
          </button>
        </div>
      </div>

      <div className={`farm-workspace ${showScene ? "" : "farm-workspace--list-only"}`}>
        {showScene && (
          <div className="farm-stage">
            {!canRender3D ? (
              <SceneUnavailable title="WebGL is unavailable">
                The interactive scene cannot start on this browser or graphics configuration. All
                placed sensors and factual telemetry remain available below.
              </SceneUnavailable>
            ) : contextLost ? (
              <SceneUnavailable title="The 3D graphics context was lost" onRetry={retryScene}>
                The browser stopped the WebGL context. The textual sensor view remains current.
              </SceneUnavailable>
            ) : (
              <SceneBoundary
                key={sceneAttempt}
                fallback={
                  <SceneUnavailable title="The 3D view could not render" onRetry={retryScene}>
                    A rendering error occurred. The textual sensor view remains current.
                  </SceneUnavailable>
                }
              >
                <Suspense
                  fallback={
                    <div className="farm-scene-state" role="status" aria-busy="true">
                      <span className="farm-scene-state__mark" aria-hidden="true">
                        3D
                      </span>
                      <div>
                        <p className="section-kicker">Presentation module</p>
                        <h3>Loading the Digital Farm</h3>
                        <p>The sensor directory remains available while the scene initializes.</p>
                      </div>
                    </div>
                  }
                >
                  <SceneComponent
                    layout={layout}
                    selectedSourceId={selectedSourceId}
                    availableSourceIds={availableSourceIds}
                    onSelectSource={setSelectedSourceId}
                    onContextLost={() => setContextLost(true)}
                    resetToken={resetToken}
                  />
                </Suspense>
              </SceneBoundary>
            )}
          </div>
        )}

        <SelectedSensor
          reading={selectedReading}
          observationsLoaded={observationsLoaded}
          observationError={observationError}
          staleAfterMs={staleAfterMs}
          now={now}
        />
      </div>

      <SensorDirectory
        readings={mapping.readings}
        selectedSourceId={selectedSourceId}
        onSelect={setSelectedSourceId}
        observationsLoaded={observationsLoaded}
      />
    </div>
  );
}
