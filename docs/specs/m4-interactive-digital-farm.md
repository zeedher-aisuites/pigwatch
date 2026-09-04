# M4 Interactive Digital Farm Specification

## Status

Implementation specification for M4. This milestone extends the accepted M3 browser application
and follows ADR-0004 without changing the M1 observation envelope, API response, persistence model,
or source lifecycle contracts. ADR-0001 through ADR-0005 remain accepted and unchanged.

## Objective

M4 gives a local developer or operator a spatial, interactive view of the deterministic M2
development sensors. The view answers where a configured sensor is presented, which exact
`source_id` it represents, what it measures, and what its latest persisted factual observation
contains. It does not interpret environment, animal health, or veterinary risk.

The evidence path remains:

```text
M2 simulator -> MQTT -> M1 ingestion -> PostgreSQL -> M1 API -> M3 telemetry hook -> M4 view
```

The Digital Farm is a presentation consumer of validated telemetry. It is not simulation ground
truth, a second telemetry client, or a new source of truth.

## Scope

M4 includes one deterministic browser-rendered development farm, descriptive spatial zones,
placements for the three existing M2 sources, selectable sensor markers, synchronized textual
selection, factual latest-observation detail, constrained orbit/pan/zoom controls, deterministic
camera reset, explicit WebGL failure handling, and an always-available non-3D equivalent.

The existing M3 telemetry console remains accessible and continues to show telemetry sources that
have no M4 placement.

## Non-goals and M5 boundary

M4 does not implement pigs, other animals, animal models or animation, animal position, tracking,
identity, behavior, physiology, feeding, drinking, weight, disease state, health scoring, anomaly
detection, predictions, veterinary thresholds, alerts, Telegram, voice, cameras, video, computer
vision, RFID, thermal imaging, sensor fusion, real hardware, LLM/RAG, workers, vehicles, weather,
pathfinding, simulation-game mechanics, facility control, paid services, or production deployment.

Webcam and recorded-video acquisition begin in M5 only. M4 defines no camera source, frame,
playback, media-storage, or vision contract.

## Spatial contract decision

The spatial representation is an explicitly M4-local, compile-time development-view configuration
under `apps/dashboard/src/digital-farm`. It is not exported from the dashboard package, persisted,
served by an API, accepted as user input, placed in a shared package, or promised as a contract for
later milestones. It can be replaced when surveyed facilities, configuration ownership, or animal
position requirements are specified.

No durable shared/public spatial schema is introduced, so no new ADR is warranted. A future
persistent or cross-service facility model would affect API/schema ownership and must stop for
Product Owner review and an ADR before implementation.

## Spatial model and telemetry separation

The local TypeScript model contains:

- one site with an ID, label, and positive dimensions;
- descriptive zones with unique IDs, labels, rectangular centers/sizes, and presentation colors;
- sensor placements with one exact M1 `source_id`, one valid zone ID, one expected existing M1
  payload type, one friendly label, and a finite three-dimensional position; and
- deterministic camera and navigation constants.

Layout validation rejects non-positive site/zone dimensions, duplicate zone IDs, duplicate sensor
`source_id` placements, unknown zone references, non-finite coordinates, and placements outside
the configured site footprint or vertical extent. These checks prevent ambiguous presentation
identity; they do not validate or mutate telemetry.

Coordinates never enter the M1 observation envelope, MQTT topic, source descriptor, database, or
API. Placements are joined to loaded telemetry only by exact `source_id`; topic strings, array
indices, display labels, and measurement types never infer location. Telemetry provenance remains
unchanged.

## Deterministic development layout

The canonical local site is `development-farm`, a generic monitored livestock shed containing Pen
A, Pen B, and a Service Aisle. Simple procedural floor, enclosure, rail, roof-support, and service
geometry establishes spatial context without external assets or animal representations.

The source-to-marker mapping uses the current M2 development identities:

| Source ID | Measurement | Zone | Position `(x, y, z)` meters |
| --- | --- | --- | --- |
| `sim-temperature-1` | Air temperature | Pen A | `(-8, 2.2, -2)` |
| `sim-humidity-1` | Relative humidity | Pen B | `(8, 2.2, -2)` |
| `sim-nh3-1` | NH3 concentration | Service Aisle | `(0, 2.2, 7)` |

These coordinates are presentation metadata, not claims that a physical or surveyed facility has
those placements.

## Coordinate system and units

World units are meters. The origin `(0, 0, 0)` is the center of the shed floor. `+x` points toward
the scene's east/right side, `+y` points upward, and `+z` points toward the service/front side.
Zone centers and sizes lie on the `x/z` floor plane; sensor positions are `x/y/z`. The site is 34 m
wide, 24 m long, and 8 m high.

No layout coordinate is embedded directly in React scene JSX. Geometry consumes the centralized
validated layout.

## Zone semantics

Zones are descriptive spatial groupings only. Pen A, Pen B, and Service Aisle carry no occupancy,
health, danger, disease, environmental threshold, or operational-control state. Color separates
areas visually but never communicates status.

## Sensor marker semantics

Each marker represents one configured placement, exact `source_id`, and measurement category.
Shape/accent differences support discovery; selected state and a factual “telemetry available” or
“no recent telemetry” state are also shown in text. Marker colors never encode safe/dangerous,
normal/abnormal, or animal health meaning. NH3 is not assigned an alarm color.

A placed source without a matching loaded observation displays `NO RECENT TELEMETRY`; no value,
timestamp, or provenance is fabricated. An observation whose source has no placement remains
available in the M3 telemetry console. The M4 directory explicitly describes itself as spatial
sensors only and reports the count of loaded unplaced source identities.

## Telemetry mapping and latest-reading behavior

M4 receives the same validated `StoredObservation[]` owned by the M3 `useTelemetry` hook. No M4
component fetches, opens MQTT, or accesses PostgreSQL. A bounded derivation builds the latest
matching observation for each placement using the existing M3 ordering: later `event_time` wins,
then lexically later `event_id` breaks equal-time ties. Measurement and unit are preserved exactly.

The expected payload type in a placement prevents a mismatched measurement from masquerading as
that marker's reading. The source linkage itself remains the exact `source_id`.

## Selection and factual detail

One React `selectedSourceId` is the sole selection state. Selecting a 3D marker or its textual
button updates that value, which highlights both representations and opens the same factual detail.
The initial selection is deterministic: the first configured placement.

When available, detail shows zone, source ID, friendly measurement, exact payload type, latest
value and unit, event time, ingest time, origin, delivery, and factual time since the event using
the M3 freshness presentation. Recorded evidence additionally shows `replay_time`; live evidence
states that replay time is not applicable. No diagnosis or threshold text is added.

## Navigation, camera, and reset

The perspective camera uses a deterministic 38-degree field of view, 0.1 m near plane, 150 m far
plane, initial position `(24, 20, 28)`, and target `(0, 0, 0)`. OrbitControls provides orbit, pan,
and wheel/pinch zoom without free-fly movement. Distance is constrained to 18–58 m, polar angle to
0.35–1.45 radians, and the target to the configured site vicinity so ordinary navigation cannot
lose the farm or clip through its floor.

The labeled Reset camera button restores the exact canonical position and target and requests one
new frame. Navigation instructions are available outside the canvas.

## Rendering and lifecycle

React Three Fiber owns the WebGL renderer and scene lifecycle. The 3D module is code-split and
loaded only when the Digital Farm view is active and WebGL is available. Rendering uses
`frameloop="demand"`; controls invalidate on interaction and telemetry/selection updates request
frames through React Three Fiber. There is no ornamental animation loop.

The scene uses only owned procedural geometries/materials and no remote models, textures, scripts,
or runtime assets. The small bounded renderer preserves its drawing buffer so demand-rendered
frames remain available to browser capture and visual QA without introducing continuous rendering.
React unmount disposes the renderer scene resources it owns. The controls effect
removes its change listener and calls `dispose()`. Context-loss listeners are installed in an
effect and removed on cleanup. Suspense/error boundaries and stable component ownership prevent a
failed render or React StrictMode probe from leaving a duplicate canvas, listener, control, or
animation loop.

## Performance budget

The primary target is a current desktop/laptop browser, including ordinary integrated graphics;
tablet is a secondary target. M4 targets:

- no more than 40 KiB gzip added to the initial M3 application chunk through view-level code
  splitting;
- no more than 300 KiB gzip for the asynchronously loaded 3D chunk and dependencies;
- fewer than 12,000 triangles, 45 draw calls, and 4 lights for the canonical scene;
- device pixel ratio capped at 1.5;
- demand-rendered idle behavior with no continuous frame loop; and
- immediate preservation of the complete textual sensor interface if 3D is hidden, unsupported,
  context-lost, or throws.

Exact bundle sizes are measured from the production build. No exact frame-rate guarantee is made
across all devices.

## Loading, empty, unavailable, and error states

The M3 hook continues to own initial API loading, API failure, last-known telemetry, readiness, and
stale policy. Within M4:

- the lazy 3D module has a purposeful loading surface;
- an empty API result leaves all configured placements visible as `NO RECENT TELEMETRY`;
- a placed source without evidence receives the same factual state;
- unplaced telemetry is counted and remains available in M3;
- unsupported WebGL explains that only the 3D presentation is unavailable;
- context loss and rendering errors replace the canvas with an explicit recoverable state; and
- an operator may intentionally hide 3D and continue with the textual interface.

No failure produces a blank or black canvas without explanatory text.

## Non-3D fallback and accessibility

The sensor directory and selected detail are normal semantic HTML and are always rendered,
regardless of 3D capability. Each placement has a keyboard-accessible selection button containing
zone, source ID, measurement, latest value/unit or no-telemetry text, and explicit origin/delivery
when evidence exists. Visible focus does not rely on color.

The canvas has a concise accessible description and is supplementary to the equivalent directory.
Controls are labeled, status messages use appropriate live/status semantics, and provenance is
textual. Selecting from either representation synchronizes the same state. M4 makes practical
accessibility provisions but does not claim formal 3D accessibility certification.

## Responsiveness and unsupported devices

Desktop uses a large scene beside the selection panel. Tablet compacts the grid while retaining
all controls. At narrow widths the scene becomes a shorter full-width region and the directory and
detail stack vertically without page-breaking overflow. A user may hide the canvas on any device;
unsupported WebGL never blocks the list or telemetry detail.

## Testing

Vitest and React Testing Library cover:

- layout validation, unique zone/source identities, valid zone references, positive dimensions,
  finite positions, site bounds, and deterministic source mapping;
- placed telemetry, missing telemetry, unplaced sources, multiple observations, equal-time
  tiebreaking, and preservation of measurement, unit, origin, and delivery;
- textual and marker-driven selection synchronization, keyboard selection, reset signaling,
  factual detail, and no-telemetry content;
- unsupported-WebGL and rendering-error fallbacks;
- scene/canvas mount, context-listener cleanup, OrbitControls disposal, unmount/remount, and
  StrictMode lifecycle behavior using focused mocks rather than pixel snapshots; and
- all existing M3 states and interactions as regression coverage.

Real-browser checks cover 1440, 1024, 820, and 390 pixel widths; scene rendering; marker selection;
orbit, pan, zoom, reset; textual access; resize; console errors; and remount cleanup. The real
product smoke sends all three actual M2 sources through MQTT, PostgreSQL, the API, and the M4
mapping before inspecting the browser result.

## Acceptance criteria

M4 is acceptable when:

1. this specification precedes substantial UI implementation;
2. no durable spatial schema or new shared/public contract is introduced;
3. the deterministic farm and descriptive zones render from centralized validated configuration;
4. all three actual M2 source IDs have one unambiguous placement;
5. source identity joins spatial metadata to the existing validated M3 telemetry boundary;
6. marker and textual selection synchronize through one state value;
7. selected detail truthfully displays value, unit, payload type, event/ingest/replay time, origin,
   delivery, and presentation freshness when available;
8. missing and unmapped telemetry remain explicit and no value is fabricated or hidden from M3;
9. constrained orbit, pan, zoom, and deterministic reset work;
10. demand rendering, bounded pixel ratio, disposal, listener cleanup, and StrictMode/remount
    behavior meet the documented lifecycle policy;
11. WebGL/loading/context/render failure has an explicit non-blank state;
12. the complete spatial sensor information remains usable through keyboard-accessible HTML;
13. representative responsive browser checks, production build, dependency audit, Docker/Compose,
    real M2 product path, and all M1–M4 tests pass; and
14. no animal, health interpretation, paid service, secret, M5, or later behavior is present.

## Known limitations

M4 has one deterministic development layout that is not a surveyed facility, persistent spatial
editor, commissioning tool, or production digital twin. Desktop/laptop is the primary 3D target.
Telemetry remains bounded HTTP polling. There are no animals, positions, tracking, cameras, RFID,
thermal data, sensor fusion, alerts, environmental/health interpretation, physical-sensor setup,
or production access-control and deployment architecture. See
[`../known-limitations/m4.md`](../known-limitations/m4.md) for the review-facing list.
