# Docker Compose Setup Guide

Complete Docker setup for running the Smrti Memory System with all required services.

## Services

The `docker-compose.yml` includes:

1. **Redis** - In-memory storage (WORKING & SHORT_TERM tiers)
2. **Qdrant** - Vector database (LONG_TERM tier)
3. **PostgreSQL** - Relational database (EPISODIC & SEMANTIC tiers)
4. **Smrti API** - FastAPI application
5. **Prometheus** - Metrics collection (optional)
6. **Grafana** - Metrics visualization (optional)

## Quick Start

### Prerequisites

- Docker 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum (8GB recommended)
- 10GB disk space

### Start All Services

```bash
# Start core services (Redis, Qdrant, PostgreSQL, API)
docker-compose up -d

# View logs
docker-compose logs -f api

# Check health
curl http://localhost:8000/health
```

### Start with Monitoring

```bash
# Include Prometheus and Grafana
docker-compose --profile monitoring up -d

# Access services
# - API: http://localhost:8000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3000 (admin/admin)
```

## Service Ports

| Service | Port | URL |
|---------|------|-----|
| Redis | 6379 | redis://localhost:6379 |
| Qdrant | 6333, 6334 | http://localhost:6333 |
| PostgreSQL | 5432 | postgresql://smrti:smrti@localhost:5432/smrti |
| API | 8000 | http://localhost:8000 |
| Prometheus | 9090 | http://localhost:9090 |
| Grafana | 3000 | http://localhost:3000 |

## Environment Variables

Create a `.env` file to override defaults:

```bash
# API Keys (comma-separated)
API_KEYS=your-secret-key-1,your-secret-key-2

# CORS Origins
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Worker processes
WORKERS=4

# Log level
LOG_LEVEL=INFO

# Embedding model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## Usage Examples

### Test API Connection

```bash
# Health check (no auth required)
curl http://localhost:8000/health

# Should return:
# {
#   "status": "healthy",
#   "version": "2.0.0",
#   "components": {
#     "redis": {"status": "healthy"},
#     "qdrant": {"status": "healthy"},
#     "postgres": {"status": "healthy"},
#     "embedding": {"status": "healthy"}
#   }
# }
```

### Store a Memory

```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:test" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "data": {
      "text": "This is a test memory"
    },
    "metadata": {
      "source": "docker-test"
    }
  }'
```

### Retrieve Memories

```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:test" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "query": "test",
    "limit": 10
  }'
```

## Database Access

### Redis CLI

```bash
# Connect to Redis
docker-compose exec redis redis-cli

# List all keys
KEYS *

# Get a key
GET working:user:test:some-uuid
```

### PostgreSQL

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U smrti -d smrti

# List tables
\dt

# Query episodic memories
SELECT namespace, data->>'text', created_at 
FROM episodic_memories 
WHERE namespace = 'user:test'
ORDER BY created_at DESC
LIMIT 10;
```

### Qdrant

```bash
# View collections
curl http://localhost:6333/collections

# Get collection info
curl http://localhost:6333/collections/smrti_user
```

## Maintenance

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f postgres
docker-compose logs -f redis
docker-compose logs -f qdrant
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api
```

### Stop Services

```bash
# Stop all (keep data)
docker-compose stop

# Stop and remove containers (keep data)
docker-compose down

# Stop and remove everything including data
docker-compose down -v
```

### Update API

```bash
# Rebuild and restart API
docker-compose build api
docker-compose up -d api
```

## Data Persistence

Data is stored in named Docker volumes:

- `smrti-redis-data` - Redis persistence (AOF)
- `smrti-qdrant-data` - Qdrant vectors
- `smrti-postgres-data` - PostgreSQL database
- `smrti-embedding-cache` - Cached embedding models

### Backup Data

```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U smrti smrti > backup.sql

# Backup Redis
docker-compose exec redis redis-cli --rdb /data/backup.rdb
docker cp smrti-redis:/data/backup.rdb ./redis-backup.rdb
```

### Restore Data

```bash
# Restore PostgreSQL
docker-compose exec -T postgres psql -U smrti smrti < backup.sql

# Restore Redis
docker cp ./redis-backup.rdb smrti-redis:/data/backup.rdb
docker-compose exec redis redis-cli --rdb /data/backup.rdb
docker-compose restart redis
```

## Monitoring

### Prometheus Metrics

Access Prometheus at http://localhost:9090

Key queries:
```promql
# Request rate
rate(smrti_http_requests_total[5m])

# Error rate
rate(smrti_http_requests_total{status="5xx"}[5m]) 
  / rate(smrti_http_requests_total[5m])

# Request duration (95th percentile)
histogram_quantile(0.95, 
  rate(smrti_http_request_duration_seconds_bucket[5m])
)

# Storage operations
rate(smrti_storage_operations_total[5m])
```

### Grafana Dashboards

1. Access Grafana at http://localhost:3000
2. Login with `admin` / `admin`
3. Import dashboard from `docker/grafana/dashboards/`

## Troubleshooting

### API Won't Start

```bash
# Check logs
docker-compose logs api

# Common issues:
# 1. Database not ready - wait for health checks
# 2. Port 8000 in use - change in docker-compose.yml
# 3. Out of memory - increase Docker memory limit
```

### Database Connection Errors

```bash
# Check database health
docker-compose ps

# All services should show "healthy" status
# If not, check specific service logs:
docker-compose logs redis
docker-compose logs postgres
docker-compose logs qdrant
```

### Slow Performance

```bash
# Check resource usage
docker stats

# If high CPU/memory:
# 1. Reduce WORKERS in .env
# 2. Increase Docker resource limits
# 3. Reduce EMBEDDING_CACHE_SIZE
```

### Reset Everything

```bash
# Nuclear option - delete all data and start fresh
docker-compose down -v
docker-compose up -d
```

## Development Mode

For local development with hot reload:

```bash
# Don't build API container, use local code
docker-compose up -d redis qdrant postgres

# Run API locally
export REDIS_URL=redis://localhost:6379/0
export QDRANT_HOST=localhost
export POSTGRES_HOST=localhost
poetry run uvicorn smrti.api.main:app --reload
```

## Production Considerations

### Security

1. **Change default passwords**:
   ```bash
   export API_KEYS=your-secure-random-keys
   export POSTGRES_PASSWORD=secure-random-password
   ```

2. **Use secrets management**:
   - Docker secrets
   - Kubernetes secrets
   - HashiCorp Vault

3. **Enable TLS**:
   - Add reverse proxy (nginx, traefik)
   - Use Let's Encrypt certificates
   - Update CORS_ORIGINS

### Scaling

1. **Horizontal scaling**:
   ```bash
   # Multiple API instances
   docker-compose up -d --scale api=3
   
   # Add load balancer (nginx, traefik)
   ```

2. **Database scaling**:
   - Redis: Cluster mode
   - Qdrant: Distributed collections
   - PostgreSQL: Read replicas

3. **Resource limits**:
   ```yaml
   # Add to docker-compose.yml
   services:
     api:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
   ```

### Monitoring

1. **Enable Prometheus**:
   ```bash
   docker-compose --profile monitoring up -d
   ```

2. **Set up alerting**:
   - Prometheus Alertmanager
   - PagerDuty integration
   - Slack notifications

3. **Log aggregation**:
   - ELK Stack
   - Grafana Loki
   - CloudWatch Logs

## Next Steps

1. Read [API Reference](../docs/API_REFERENCE.md)
2. Review [Architecture Documentation](../docs/prompts/smrti_architecture.md)
3. Run [Integration Tests](../tests/integration/README.md)
4. Deploy to production (see deployment guide)

## Support

For issues and questions:
- GitHub Issues: https://github.com/konf-dev/smrti/issues
- Documentation: https://github.com/konf-dev/smrti/docs
