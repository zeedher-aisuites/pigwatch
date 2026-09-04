# Product Roadmap

| Milestone | Scope |
| --- | --- |
| M0 | Engineering foundation |
| M1 | Telemetry core |
| M2 | Sensor simulator |
| M3 | Basic dashboard |
| M4 | Interactive Digital Farm |
| M5 | Webcam/video ingestion |
| M6 | Animal detection |
| M7 | Tracking |
| M8 | Identity + RFID simulation |
| M9 | Thermal simulation |
| M10 | Sensor fusion |
| M11 | Anomaly engine |
| M12 | Telegram alerts |
| M13 | Voice alerts |
| M14 | Animal health timeline |
| M15 | Predictive models |
| M16 | Veterinary RAG |
| M17 | Real hardware adapters |

Milestone boundaries are deliberate. A milestone may refine interfaces needed by its capability, but it should not pull later product behavior forward without a documented decision.

M0, M1, M2, and M3 are closed. M4 is the current implementation milestone: it presents the three
deterministic development sensor identities in a browser-based farm and joins their placements to
the accepted M3 telemetry boundary. The layout is local presentation configuration rather than a
shared facility schema. It does not add animal simulation, inferred health state, anomaly behavior,
or camera/video behavior. M5 remains next and has not started.

The M4 Digital Farm is browser-based using React, TypeScript, Three.js, and React Three Fiber. Godot
and Unreal Engine remain possible future tools only if browser-based simulation eventually proves
insufficient; neither is a current roadmap dependency.
