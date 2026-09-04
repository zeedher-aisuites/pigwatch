# Local Infrastructure

`compose.yaml` provides PostgreSQL and Eclipse Mosquitto alongside development images for the API
and dashboard. M1 enables Mosquitto persistence in a named local volume so QoS 1 persistent-session
behavior can be tested. Anonymous MQTT ports are hard-bound to host loopback for isolated local
development and must not be exposed to a shared network. This directory holds service-specific
configuration only. Production authentication, TLS, secrets, backups and deployment policies remain
out of scope.
