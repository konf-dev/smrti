# Smrti API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication

All endpoints (except `/health`, `/docs`, `/metrics`) require:

```http
Authorization: Bearer <api_key>
X-Namespace: <namespace>
```

**Default API Key** (development): `dev-key-123`

**Namespace Format**: `part1:part2[:part3...]` (minimum 2 parts)

Examples:
- ✅ `user:123`
- ✅ `org:acme:project:alpha`
- ✅ `tenant:prod:service:memory`
- ❌ `invalid` (single part)

---

## Endpoints

### Health Check

```http
GET /health
```

**No authentication required**

**Response** (200 OK):
```json
{
  "status": "healthy",
  "version": "2.0.0",
  "timestamp": "2025-01-14T12:34:56.789Z",
  "components": {
    "redis": {"status": "healthy"},
    "qdrant": {"status": "healthy"},
    "postgres": {"status": "healthy"},
    "embedding": {"status": "healthy"}
  }
}
```

---

### Store Memory

```http
POST /memory/store
```

**Authentication required**

**Request Body**:
```json
{
  "memory_type": "WORKING" | "SHORT_TERM" | "LONG_TERM" | "EPISODIC" | "SEMANTIC",
  "data": {
    "text": "Memory content (required)",
    "custom_field": "any additional data"
  },
  "metadata": {
    "key": "value",
    "nested": {"allowed": true}
  }
}
```

**Response** (201 Created):
```json
{
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "memory_type": "WORKING",
  "namespace": "user:123",
  "created_at": "2025-01-14T12:34:56.789Z"
}
```

**Example**:
```bash
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "data": {
      "text": "User completed workout session",
      "event_type": "workout_completed",
      "duration_minutes": 45
    },
    "metadata": {
      "impact": "high",
      "category": "fitness"
    }
  }'
```

---

### Retrieve Memories

```http
POST /memory/retrieve
```

**Authentication required**

**Request Body**:
```json
{
  "memory_type": "WORKING" | "SHORT_TERM" | "LONG_TERM" | "EPISODIC" | "SEMANTIC",
  "query": "search query or question",
  "filters": {
    "field": "value"
  },
  "limit": 10
}
```

**Fields**:
- `memory_type` (required): Tier to search
- `query` (optional): Search query (semantic for LONG_TERM, text for others)
- `filters` (optional): Additional filter criteria
- `limit` (optional): Max results (1-100, default: 10)

**Response** (200 OK):
```json
{
  "memories": [
    {
      "memory_id": "550e8400-e29b-41d4-a716-446655440000",
      "memory_type": "EPISODIC",
      "namespace": "user:123",
      "data": {
        "text": "User completed workout session",
        "event_type": "workout_completed",
        "duration_minutes": 45
      },
      "metadata": {
        "impact": "high",
        "category": "fitness"
      },
      "created_at": "2025-01-14T12:34:56.789Z",
      "relevance_score": 0.95
    }
  ],
  "count": 1,
  "memory_type": "EPISODIC"
}
```

**Example - WORKING tier (text search)**:
```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "query": "workout",
    "limit": 5
  }'
```

**Example - LONG_TERM tier (semantic search)**:
```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "LONG_TERM",
    "query": "What are the benefits of regular exercise?",
    "limit": 10
  }'
```

**Example - EPISODIC tier (with filters)**:
```bash
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "query": "workout",
    "filters": {
      "event_type": "workout_completed"
    },
    "limit": 20
  }'
```

---

### Delete Memory

```http
DELETE /memory/{memory_type}/{memory_id}
```

**Authentication required**

**Path Parameters**:
- `memory_type`: `working`, `short_term`, `long_term`, `episodic`, or `semantic` (lowercase)
- `memory_id`: UUID of the memory

**Response** (200 OK):
```json
{
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "deleted": true,
  "memory_type": "EPISODIC"
}
```

**Response** (404 Not Found):
```json
{
  "detail": "Memory 550e8400-e29b-41d4-a716-446655440000 not found in EPISODIC tier"
}
```

**Example**:
```bash
curl -X DELETE http://localhost:8000/memory/episodic/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123"
```

---

### Prometheus Metrics

```http
GET /metrics
```

**No authentication required**

**Response**: Prometheus text format

**Example**:
```bash
curl http://localhost:8000/metrics
```

**Key Metrics**:
- `smrti_http_requests_total` - Total HTTP requests by method, endpoint, status
- `smrti_http_request_duration_seconds` - Request duration histogram
- `smrti_storage_operations_total` - Storage operations by operation, memory_type, status
- `smrti_storage_operation_duration_seconds` - Storage operation duration
- `smrti_embedding_generations_total` - Embeddings generated by status
- `smrti_embedding_cache_hits_total` - Embedding cache hits
- `smrti_embedding_cache_misses_total` - Embedding cache misses

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid memory_type. Must be one of: WORKING, SHORT_TERM, LONG_TERM, EPISODIC, SEMANTIC"
}
```

### 401 Unauthorized
```json
{
  "detail": "Invalid API key"
}
```

### 404 Not Found
```json
{
  "detail": "Memory 550e8400-e29b-41d4-a716-446655440000 not found in WORKING tier"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to store memory: Storage backend unavailable"
}
```

---

## Memory Types

| Type | Storage | TTL | Search Method | Use Case |
|------|---------|-----|---------------|----------|
| **WORKING** | Redis | 5 min | Text match | Current context, immediate tasks |
| **SHORT_TERM** | Redis | 1 hour | Text match + time order | Session summary, recent history |
| **LONG_TERM** | Qdrant | ∞ | Vector similarity | Semantic facts, knowledge base |
| **EPISODIC** | PostgreSQL | ∞ | Time-range + full-text | Event timeline, temporal queries |
| **SEMANTIC** | PostgreSQL | ∞ | Entity/relationship | Knowledge graph, structured data |

---

## API Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## Common Patterns

### Store and Retrieve Workflow
```bash
# 1. Store memory
MEMORY_ID=$(curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{"memory_type": "WORKING", "data": {"text": "Test"}}' \
  | jq -r '.memory_id')

# 2. Retrieve memories
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{"memory_type": "WORKING", "query": "Test", "limit": 10}'

# 3. Delete memory
curl -X DELETE http://localhost:8000/memory/working/$MEMORY_ID \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123"
```

### Multi-Tier Storage Pattern
```bash
# Store same content in multiple tiers for different retention
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "WORKING",
    "data": {"text": "Important event happened"},
    "metadata": {"priority": "high"}
  }'

curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: user:123" \
  -H "Content-Type: application/json" \
  -d '{
    "memory_type": "EPISODIC",
    "data": {"text": "Important event happened"},
    "metadata": {"priority": "high"}
  }'
```

### Namespace Isolation
```bash
# Different namespaces see different data
curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: tenant:a:user:1" \
  -d '{"memory_type": "WORKING", "data": {"text": "Tenant A data"}}'

curl -X POST http://localhost:8000/memory/store \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: tenant:b:user:1" \
  -d '{"memory_type": "WORKING", "data": {"text": "Tenant B data"}}'

# Retrieval respects namespace
curl -X POST http://localhost:8000/memory/retrieve \
  -H "Authorization: Bearer dev-key-123" \
  -H "X-Namespace: tenant:a:user:1" \
  -d '{"memory_type": "WORKING", "query": "data"}'
# Returns only "Tenant A data"
```

---

## Running the Server

### Development Mode
```bash
# With poetry
poetry run smrti

# With uvicorn directly (auto-reload)
poetry run uvicorn smrti.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Production Mode
```bash
# Multiple workers
WORKERS=4 poetry run smrti

# With environment variables
export API_KEYS="key1,key2,key3"
export LOG_LEVEL="WARNING"
poetry run smrti
```

---

## Environment Variables

See `.env.example` for full list. Key variables:

```bash
# API Configuration
API_VERSION=2.0.0
API_KEYS=dev-key-123,another-key
CORS_ORIGINS=*

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4
LOG_LEVEL=INFO

# Redis
REDIS_URL=redis://localhost:6379/0

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=smrti
POSTGRES_USER=smrti
POSTGRES_PASSWORD=smrti

# Embedding
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_CACHE_SIZE=10000
```

---

*For full documentation, see README.md and /docs endpoint*
