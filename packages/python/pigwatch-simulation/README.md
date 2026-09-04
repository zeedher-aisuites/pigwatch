# pigwatch-simulation

M2 implementation of deterministic synthetic environmental sources. It supports the three scalar
M1 measurements—temperature (`Cel`), relative humidity (`%`), and ammonia concentration (`[ppm]`)—
in static and periodic modes.

Sources implement the accepted lifecycle, use injectable clocks and independent seeded random
state, and publish immutable `SYNTHETIC` + `LIVE` `ObservationEnvelopeV1` values only through the M1
MQTT publisher. The bounded random walk is an infrastructure test/demo signal, not a calibrated farm
model or veterinary threshold.

From the repository root, after the API is ready:

```bash
uv run pigwatch-simulator --config configs/simulator.development.json
```

See [`docs/specs/m2-sensor-simulator.md`](../../../docs/specs/m2-sensor-simulator.md) for the exact
configuration, determinism, scheduling, lifecycle, retry, and failure contracts.
