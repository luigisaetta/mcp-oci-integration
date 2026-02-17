# Deployment Layout

This folder contains deployment assets for containerized runs.

## Structure

- `deploy/compose/docker-compose.local.yml`: local Docker Compose stack for MCP servers + aggregator
- `deploy/config/aggregator_config.docker.yaml`: aggregator config used by Compose
- `deploy/docker/requirements.mcp-local.txt`: slim Python requirements used by Docker image builds

## Quick Start

Run from repository root:

```bash
docker compose -f deploy/compose/docker-compose.local.yml up --build -d
```

Stop:

```bash
docker compose -f deploy/compose/docker-compose.local.yml down
```

## Notes

- The Compose file uses build context `../..` so it can reference the root `Dockerfile` and project source code.
- Aggregator in Compose is started with:
  - `python mcp_aggregator.py --config deploy/config/aggregator_config.docker.yaml`
