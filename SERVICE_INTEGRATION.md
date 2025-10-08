# Service Integration Guide: Using the Shared Infrastructure

This guide explains how any service (e.g., Smrti, Gateway, Tools) can connect to the shared infrastructure in this repo: PostgreSQL, Redis, MinIO (S3), Qdrant, ClickHouse, and Langfuse.

You can integrate in two ways:
- Same-network: attach your service containers to the same Docker network to use service DNS names like `postgres`, `redis`, etc. (preferred on the same host)
- Host-port: connect via the VPS host IP and published ports (works for processes not on the same Docker network or on other hosts)

---

## What’s running and where

- Postgres: service name `postgres` → host port 5432
- Redis: service name `redis` → host port 6379
- MinIO: service name `minio` → host ports 9000 (API), 9001 (Console)
- Qdrant: service name `qdrant` → host ports 6333 (HTTP), 6334 (gRPC)
- ClickHouse: service name `clickhouse` → host ports 8123 (HTTP), 9440 (native TCP)
- Langfuse: service name `langfuse-server` (container: `konf-langfuse`) → host port 3000

Notes
- Default database names include: `konf_gateway`, `konf_tools`, `konf_smrti`, `langfuse` (see `init-databases.sql`).
- Credentials and secrets are provided via environment variables; see `.env.example`.

---

## Option A: Same Docker network (preferred)

Attach your service’s compose project to the existing network so you can use container DNS names (e.g., `postgres`, `redis`, `minio`, `qdrant`, `clickhouse`) without exposing additional ports.

1) Find the network name (created by this stack):
  - Name: `konf-dev-infra-network` (set in docker-compose.yml)
  - Verify on the host: `docker network ls | grep konf-dev-infra-network`

2) In your service’s `docker-compose.yml`, declare the external network and join it:

```yaml
networks:
  konf-network:
    external: true
    name: konf-dev-infra-network  # use the shared infra network

services:
  your-service:
    image: your/image:tag
    # ...
    networks:
      - konf-network
    environment:
      # Postgres (choose your db)
      DATABASE_URL: postgresql://konf:${POSTGRES_PASSWORD}@postgres:5432/konf_smrti

      # Redis
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0

      # MinIO (S3)
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY_ID: ${MINIO_ROOT_USER}
      S3_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}
      S3_REGION: us-east-1
      S3_FORCE_PATH_STYLE: "true"

      # Qdrant
      QDRANT_URL: http://qdrant:6333
      # QDRANT_API_KEY: ${QDRANT_API_KEY}  # if you enable auth

      # ClickHouse (HTTP and/or native)
      CLICKHOUSE_HTTP_URL: http://clickhouse:8123
      CLICKHOUSE_USER: ${CLICKHOUSE_USER}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
      CLICKHOUSE_NATIVE_DSN: clickhouse://clickhouse:9000
```

3) Use the `.env` file (see `.env.example`) to supply secrets referenced in your compose file.

---

## Option B: Host-port connectivity

If you cannot (or don’t want to) share the Docker network, connect to the VPS host IP using the published ports.

- Replace hosts in your URLs with the VPS IP or DNS, e.g. `db.example.com`:
  - Postgres: `postgresql://konf:${POSTGRES_PASSWORD}@<VPS-IP>:5432/<db>`
  - Redis: `redis://:${REDIS_PASSWORD}@<VPS-IP>:6379/0`
  - MinIO API: `http://<VPS-IP>:9000`
  - Qdrant HTTP: `http://<VPS-IP>:6333`
  - ClickHouse HTTP: `http://<VPS-IP>:8123` (native TCP: `<VPS-IP>:9440`)
  - Langfuse UI/API: `http://<VPS-IP>:3000`

Linux containers on the same host cannot use `localhost` to reach services published on the host; use the host IP address or DNS.

---

## Connection strings and env vars (copy/paste)

PostgreSQL
- User: `konf`
- Password: `${POSTGRES_PASSWORD}`
- Databases: `konf_gateway`, `konf_tools`, `konf_smrti`, `langfuse`
- Example: `postgresql://konf:${POSTGRES_PASSWORD}@postgres:5432/konf_smrti`

Redis
- Example: `redis://:${REDIS_PASSWORD}@redis:6379/0`

MinIO (S3-compatible)
- Endpoint: `http://minio:9000`
- Region: `us-east-1`
- Path-style: `true`
- Buckets created: `konf-agents`, `konf-tools`, `konf-backups`
- Example SDK config: endpoint, accessKeyId, secretAccessKey, region, forcePathStyle

Qdrant
- HTTP: `http://qdrant:6333`
- gRPC: `qdrant:6334`
- (Enable API key if needed; then set `QDRANT_API_KEY` on clients.)

ClickHouse
- HTTP URL: `http://clickhouse:8123`
- Native DSN: `clickhouse://clickhouse:9000`
- Auth: `${CLICKHOUSE_USER}` / `${CLICKHOUSE_PASSWORD}`

Langfuse (optional client integration)
- Base URL: `http://<VPS-IP>:3000`
- Acquire project keys from Langfuse UI and set in your service.

---

## Healthchecks (recommended)

Adopt these patterns so your services behave well under compose:

- Postgres: `pg_isready -U konf`
- Redis: `redis-cli --raw incr ping`
- MinIO: `curl -f http://localhost:9000/minio/health/live`
- Qdrant: TCP connect to 6333 or HTTP GET /readyz (image often lacks curl/wget)
- ClickHouse: `wget --spider -q http://localhost:8123/ping`
- Your service: expose a `/health` endpoint or use a TCP connect check for the listening port.

Example (service):
```yaml
healthcheck:
  test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/127.0.0.1/8080' "]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 60s
```

---

## Security and operations

- Change all default passwords in your `.env`.
- Prefer the shared Docker network for intra-host access; avoid exposing ports publicly when not needed.
- If internet exposure is required, put services behind Traefik or another reverse proxy with TLS.
- Backups: persist volumes are already configured under `/mnt/konf-dev-volume-1/*`. Add scheduled backups for Postgres and MinIO buckets as needed.

---

## Troubleshooting

- Can’t resolve `postgres` from your service? Ensure it joined the external network `ideas-and-docs_konf-network`.
- Can’t reach via host-port from another container? Use the VPS IP (not `localhost`) or join the shared network instead.
- Healthcheck flapping? Increase `start_period` and `retries`, and prefer TCP checks for images without curl/wget.

---

## Minimal example for a service (Smrti)

```yaml
version: "3.9"

networks:
  konf-network:
    external: true
  name: konf-dev-infra-network

services:
  smrti:
    image: yourorg/smrti:latest
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql://konf:${POSTGRES_PASSWORD}@postgres:5432/konf_smrti
      REDIS_URL: redis://:${REDIS_PASSWORD}@redis:6379/0
      S3_ENDPOINT: http://minio:9000
      S3_ACCESS_KEY_ID: ${MINIO_ROOT_USER}
      S3_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}
      S3_REGION: us-east-1
      S3_FORCE_PATH_STYLE: "true"
      QDRANT_URL: http://qdrant:6333
      CLICKHOUSE_HTTP_URL: http://clickhouse:8123
      CLICKHOUSE_USER: ${CLICKHOUSE_USER}
      CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD}
    networks:
      - konf-network
    healthcheck:
      test: ["CMD-SHELL", "bash -c 'echo > /dev/tcp/127.0.0.1/8080' "]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 60s
```

Keep `.env` beside your service compose file and fill secrets from the example below.

---

## Next steps

- Copy `.env.example` to your service repo and fill real values.
- Attach your service to `konf-dev-infra-network` or use host-port mode.
- Verify with a simple smoke test and healthchecks.
