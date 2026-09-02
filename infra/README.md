# Local Infrastructure

`compose.yaml` provides PostgreSQL and Eclipse Mosquitto alongside development images for the API and dashboard. Anonymous MQTT ports are hard-bound to host loopback for isolated local development and must not be exposed to a shared network. This directory holds service-specific configuration only. Production infrastructure, secrets, backups, and deployment policies are outside M0.
