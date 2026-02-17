# Docker Compose Commands (Local MCP Stack)

These commands refer to:

- `deploy/compose/docker-compose.local.yml`

Run them from the project root.

## One-Time Setup

Create your local env file (contains sensitive values, not committed):

```bash
cp .env.example .env
```

Then edit `.env` and set:

- `VECTOR_DB_USER`
- `VECTOR_DB_PWD`
- `VECTOR_WALLET_PWD`
- `VECTOR_DSN`
- `VECTOR_WALLET_DIR_HOST`

## Start

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml up --build -d
```

## Stop and Remove

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml down
```

## Show Running Services

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml ps
```

## Show Logs (All Services)

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f
```

## Show Logs (Single Service)

```bash
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_aggregator
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_consumption
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_agenda
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_internet_search
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_semantic_search
docker compose --env-file .env -f deploy/compose/docker-compose.local.yml logs -f mcp_employee
```
