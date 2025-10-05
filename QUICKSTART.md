# Smrti v2.0 - Quick Start Guide

Get Smrti running in 5 minutes with Docker Compose.

## Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- 4GB RAM available
- 10GB disk space

## 1. Clone and Start

```bash
# Clone repository (if not already)
cd /home/bert/Work/orgs/konf-dev/smrti

# Start all services
docker-compose up -d

# Wait for services to be healthy (30-60 seconds)
watch docker-compose ps
# All services should show "healthy" status
```

## 2. Verify Health

```bash
# Check API health
curl http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "version": "2.0.0",
#   "timestamp": "2025-10-05T12:00:00Z",
#   "components": {
#     "redis": {"status": "healthy"},
#     "qdrant": {"status": "healthy"},
#     "postgres": {"status": "healthy"},
#     "embedding": {"status": "healthy"}
#   }
# }
```

## 3. Store Your First Memory

```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "data": {
      "text": "Hello, Smrti! This is my first memory."
    },
    "metadata": {
      "source": "quick-start",
      "importance": "high"
    }
  }'

# Response:
# {
#   "memory_id": "550e8400-e29b-41d4-a716-446655440000",
#   "memory_type": "WORKING",
#   "namespace": "user:demo",
#   "created_at": "2025-10-05T12:00:00Z"
# }
```

## 4. Retrieve Memories

```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "query": "first memory",
    "limit": 10
  }'

# Response:
# {
#   "memories": [
#     {
#       "memory_id": "550e8400-e29b-41d4-a716-446655440000",
#       "memory_type": "WORKING",
#       "namespace": "user:demo",
#       "data": {
#         "text": "Hello, Smrti! This is my first memory."
#       },
#       "metadata": {
#         "source": "quick-start",
#         "importance": "high"
#       },
#       "created_at": "2025-10-05T12:00:00Z",
#       "relevance_score": 0.95
#     }
#   ],
#   "count": 1,
#   "memory_type": "WORKING"
# }
```

## 5. Try Different Memory Tiers

### WORKING Memory (5-minute TTL)
Current context, immediate tasks
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{"memory_type": "WORKING", "data": {"text": "Currently working on project X"}}'
```

### SHORT_TERM Memory (1-hour TTL)
Session summary, recent history
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{"memory_type": "SHORT_TERM", "data": {"text": "Completed 3 tasks today"}}'
```

### LONG_TERM Memory (Persistent, Vector Search)
Semantic facts, knowledge base
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{"memory_type": "LONG_TERM", "data": {"text": "Python is a high-level programming language"}}'
```

### EPISODIC Memory (Persistent, Time-based)
Event timeline, temporal queries
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "data": {
      "text": "User completed workout",
      "event_type": "goal_achieved"
    }
  }'
```

### SEMANTIC Memory (Persistent, Knowledge Graph)
Structured knowledge, entity relationships
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:demo" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "SEMANTIC",
    "data": {
      "text": "Paris is the capital of France",
      "entities": [
        {"id": "paris", "type": "city"},
        {"id": "france", "type": "country"}
      ],
      "relationships": [
        {"from": "paris", "to": "france", "type": "capital_of"}
      ]
    }
  }'
```

## 6. Explore the API

### Interactive Documentation
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Prometheus Metrics
http://localhost:8000/metrics

### Monitoring (Optional)
```bash
# Start monitoring stack
docker-compose --profile monitoring up -d

# Access Grafana
open http://localhost:3000  # admin/admin
```

## Next Steps

1. **Read the Docs**:
   - [API Reference](docs/API_REFERENCE.md)
   - [Architecture Guide](docs/prompts/smrti_architecture.md)
   - [Docker Setup Guide](docker/README.md)

2. **Run Tests**:
   ```bash
   # Unit tests
   poetry install
   poetry run pytest tests/unit/ -v
   
   # Integration tests (requires Docker services)
   poetry run pytest tests/integration/ -v
   ```

3. **Configure for Production**:
   - Change API keys in `.env`
   - Configure CORS origins
   - Set up TLS/HTTPS
   - Enable monitoring

## Troubleshooting

### Services Won't Start
```bash
# Check logs
docker-compose logs -f

# Restart a service
docker-compose restart api

# Reset everything
docker-compose down -v
docker-compose up -d
```

### API Returns 401
- Check API key: `dev-key-123` is the default
- Verify Authorization header: `Bearer <key>`
- Check X-Namespace header is present

### Database Errors
```bash
# Check service health
docker-compose ps

# View specific service logs
docker-compose logs postgres
docker-compose logs redis
docker-compose logs qdrant
```

## Support

- Documentation: [README.md](README.md)
- Issues: https://github.com/konf-dev/smrti/issues
- Architecture: [smrti_architecture.md](docs/prompts/smrti_architecture.md)

---

**You're ready to use Smrti! 🚀**
