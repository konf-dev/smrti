# Master Prompt: Build Smrti v2.0 Memory Storage System

**To:** AI Development Agent  
**Task:** Build production-grade multi-tier memory storage system from scratch  
**Reference:** `prds/smrti_prd_v2.md` (complete specification)  
**Timeline:** 21 days (3 weeks)  
**Quality Standard:** Production-ready, 90%+ test coverage, no compromises

---

## Your Mission

You are building **Smrti v2.0**, a specialized storage system for agentic AI applications. This is a **complete rewrite** with clean architecture, not a refactor of legacy code.

### Critical Context

**What Smrti IS:**
- Pure storage and retrieval layer for 5 memory types
- Protocol-based, pluggable adapter architecture
- Multi-tenant from day one
- Production-quality code (tests, observability, security)

**What Smrti IS NOT:**
- An intelligent classification system (that's Sutra's job)
- A consolidation engine (build later with agents)
- A monolithic system (everything is swappable)

---

## Core Directives

### 1. Read the PRD First

Before writing ANY code:
1. Read `prds/smrti_prd_v2.md` cover to cover
2. Understand the separation of concerns
3. Review all API specifications
4. Study database schemas
5. Understand the adapter protocol

**Ask questions if ANYTHING is unclear. Do not assume.**

### 2. Code Quality Standards

This is production code for a startup that means business. Quality is non-negotiable.

**Required Standards:**
- ✅ Type hints on ALL functions and methods
- ✅ Docstrings on ALL public interfaces (Google style)
- ✅ Async/await for ALL I/O operations
- ✅ Error handling for ALL failure cases
- ✅ Input validation for ALL user inputs
- ✅ Tests for ALL functionality (90%+ coverage)
- ✅ Structured logging for ALL operations
- ✅ Metrics for ALL critical paths

**Code Style:**
- Use `black` formatter (line length 100)
- Use `ruff` linter (strict mode)
- Use `mypy` for type checking (strict mode)
- Follow PEP 8 conventions

**No Shortcuts:**
- No `# type: ignore` without explanation
- No `pass` in except blocks
- No `print()` statements (use logging)
- No hardcoded values (use config)
- No commented-out code

### 3. Testing Philosophy

**Tests are NOT optional. They are the product.**

**Test Hierarchy:**
1. **Unit tests** (fast, isolated, mock external deps)
   - Test each adapter independently
   - Test embedding providers
   - Test validation logic
   - Test utilities

2. **Integration tests** (use real test databases)
   - Test Redis operations
   - Test Qdrant operations
   - Test Postgres operations
   - Test API endpoints end-to-end

3. **E2E tests** (full stack with docker-compose)
   - Test multi-tenant isolation
   - Test full memory lifecycle
   - Test error scenarios
   - Test performance under load

**Test-Driven Development:**
- Write tests BEFORE implementation (when possible)
- Test happy path AND error cases
- Test boundary conditions
- Test multi-tenant isolation paranoidly

**Coverage Requirements:**
- Overall: ≥ 90%
- Critical paths (auth, storage, API): 100%
- Every error handler: tested

### 4. Separation of Concerns

The architecture has clear boundaries. Respect them.

```
API Layer (routes, middleware)
    ↓ calls
Storage Manager (routes to adapters)
    ↓ uses
Storage Adapters (implement protocol)
    ↓ talk to
Physical Storage (Redis, Qdrant, Postgres)

Embedding Service (independent)
    ↓ used by
Storage Manager (for vector memories)
```

**Rules:**
- API layer NEVER talks directly to databases
- Storage adapters NEVER import from API layer
- Each layer only knows about the layer below
- Use dependency injection everywhere

### 5. Legacy Code Policy

There is legacy code in `legacy_code/` directory of the Smrti repo.

**Rules for Legacy Code:**
- ✅ You MAY look at it for reference
- ✅ You MAY understand the concepts
- ✅ You MAY reuse test fixtures/data
- ❌ You MUST NOT copy-paste code
- ❌ You MUST NOT import from legacy
- ❌ You MUST NOT preserve broken patterns

**Why?** The legacy code has incomplete implementations, mixed concerns, and broken abstractions. Starting fresh is faster than fixing.

**When to reference legacy:**
- Understanding memory tier concepts
- Seeing what didn't work (learn from mistakes)
- Getting test data examples

### 6. Configuration Management

All configuration via environment variables. No hardcoded values.

**Pattern:**
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Server
    port: int = 8000
    host: str = "0.0.0.0"
    workers: int = 4
    
    # Redis
    redis_url: str
    redis_working_ttl: int = 300
    
    # Qdrant
    qdrant_url: str
    qdrant_vector_size: int = 384
    
    # Postgres
    postgres_url: str
    
    # Embedding
    embedding_provider: Literal["local", "api"]
    embedding_model: str
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()
```

**Rules:**
- All settings in one place
- Validation on startup (fail fast)
- Type-safe access
- Defaults for development
- Required values for production

### 7. Error Handling Strategy

Errors are data. Handle them gracefully.

**Error Hierarchy:**
```python
class SmrtiError(Exception):
    """Base exception for all Smrti errors"""
    pass

class ValidationError(SmrtiError):
    """Invalid input data"""
    pass

class StorageError(SmrtiError):
    """Database operation failed"""
    pass

class EmbeddingError(SmrtiError):
    """Embedding generation failed"""
    pass

class AuthenticationError(SmrtiError):
    """Invalid/missing API key"""
    pass
```

**Error Response Pattern:**
```python
from fastapi import HTTPException

def validate_namespace(namespace: str) -> None:
    if not re.match(r'^[a-zA-Z0-9:_-]+$', namespace):
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": "Namespace contains invalid characters",
                "field": "namespace"
            }
        )
```

**Retry Logic:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
async def store_with_retry(...):
    # Storage operation that might fail transiently
    pass
```

### 8. Logging Standards

Structured JSON logging for production observability.

**Log Levels:**
- `DEBUG`: Development only, verbose
- `INFO`: Normal operations (request/response, success)
- `WARNING`: Recoverable errors (retry succeeded)
- `ERROR`: Failures (with context for debugging)
- `CRITICAL`: System-level failures

**Log Format:**
```python
import structlog

logger = structlog.get_logger()

# Good logging
logger.info(
    "memory_stored",
    memory_id=str(memory_id),
    memory_type=memory_type,
    namespace=namespace,
    duration_ms=duration * 1000
)

# Bad logging
logger.info(f"Stored memory {memory_id}")
```

**What to Log:**
- Every API request (method, path, status, duration)
- Every storage operation (type, namespace, success/failure)
- Every error (with full context, no PII)
- Performance metrics (slow queries, long embeddings)

**What NOT to Log:**
- API keys
- Full memory content (PII risk)
- Passwords or secrets
- User embeddings (too large)

### 9. Performance Considerations

**Async Everything:**
```python
# Good
async def store_memory(...):
    async with redis_client.pipeline() as pipe:
        await pipe.set(...)
        await pipe.expire(...)
        await pipe.execute()

# Bad
def store_memory(...):
    redis_client.set(...)
    redis_client.expire(...)
```

**Connection Pooling:**
- Redis: Reuse connection pool
- Postgres: Use asyncpg with pool
- Qdrant: HTTP client with keep-alive

**Caching:**
- Cache embeddings (hash of text → vector)
- Cache API key validation
- Don't cache memory content (defeats purpose)

**Batch Operations:**
- Not in v1 (keep it simple)
- Can add in v2 if needed

### 10. Security Checklist

**Input Validation:**
- Validate ALL user inputs
- Sanitize namespace strings
- Limit text length (prevent DoS)
- Validate JSON structure

**SQL Injection Prevention:**
```python
# Good
await db.execute(
    "SELECT * FROM memories WHERE namespace = $1",
    namespace
)

# Bad
await db.execute(
    f"SELECT * FROM memories WHERE namespace = '{namespace}'"
)
```

**API Key Security:**
- Constant-time comparison
- Never log keys
- Support rotation
- Validate on every request

**Multi-Tenancy Isolation:**
- ALWAYS filter by namespace
- Test isolation paranoidly
- Audit all queries for leaks

---

## Development Workflow

### Phase 1: Project Setup (Day 1-2)

**Tasks:**
1. Initialize Python project with Poetry
   ```bash
   poetry init
   poetry add fastapi uvicorn[standard] redis qdrant-client asyncpg
   poetry add sentence-transformers httpx pydantic-settings structlog
   poetry add --group dev pytest pytest-asyncio pytest-cov black ruff mypy
   ```

2. Create directory structure (see PRD)
   ```
   src/
   ├── api/
   ├── storage/
   ├── embedding/
   ├── core/
   └── utils/
   tests/
   ├── unit/
   ├── integration/
   └── e2e/
   docker/
   scripts/
   config/
   ```

3. Set up configuration system
   - `src/core/config.py` with Pydantic Settings
   - `.env.example` with all variables
   - Validation on startup

4. Set up logging and metrics
   - Structured logging with structlog
   - Prometheus metrics with prometheus-client
   - Health check endpoint

5. Set up testing infrastructure
   - `pytest.ini` configuration
   - `conftest.py` with fixtures
   - Docker Compose for test databases

**Deliverable:** Empty project structure with config, logging, basic tests

---

### Phase 2: Storage Protocol & Adapters (Day 3-9)

**Day 3-4: Redis Adapters**

1. Define `StorageAdapter` protocol in `src/storage/protocol.py`
   ```python
   from typing import Protocol, Optional, List, Dict, Any
   from uuid import UUID
   
   class StorageAdapter(Protocol):
       async def store(...) -> UUID: ...
       async def retrieve(...) -> List[Dict]: ...
       async def get(...) -> Optional[Dict]: ...
       async def delete(...) -> bool: ...
       async def health_check(...) -> Dict: ...
   ```

2. Implement `RedisWorkingAdapter`
   - TTL: 300 seconds (5 minutes)
   - Key pattern: `working:{namespace}:{memory_id}`
   - Retrieval: scan pattern, return recent N
   - Unit tests with fakeredis
   - Integration tests with real Redis

3. Implement `RedisShortTermAdapter`
   - TTL: 3600 seconds (1 hour)
   - Key pattern: `short_term:{namespace}:{memory_id}`
   - Similar to working but longer TTL
   - Sorted sets for time-ordering
   - Tests

**Day 5-7: Qdrant Adapter**

4. Implement `QdrantLongTermAdapter`
   - Collection per namespace prefix
   - Store text + embedding + metadata
   - Vector similarity search
   - Metadata filtering
   - Health check (collection exists)
   - Unit tests (mock Qdrant client)
   - Integration tests (real Qdrant)

**Day 8-9: Postgres Adapters**

5. Create database schemas
   - `scripts/init_db.sql` (see PRD)
   - Episodic and Semantic tables
   - Indexes for performance
   - Test on fresh DB

6. Implement `PostgresEpisodicAdapter`
   - Store events with timestamps
   - Time-range queries
   - Full-text search
   - Event type filtering
   - Tests

7. Implement `PostgresSemanticAdapter`
   - Store facts with entities/relationships
   - JSONB queries
   - Entity lookup
   - Relationship traversal
   - Tests

**Deliverable:** All 5 adapters working with 100% test coverage

---

### Phase 3: Embedding Service (Day 10-11)

**Day 10: Embedding Protocol & Local Provider**

1. Define `EmbeddingProvider` protocol
   ```python
   class EmbeddingProvider(Protocol):
       async def embed(self, texts: List[str]) -> List[List[float]]: ...
       def dimension(self) -> int: ...
       async def health_check(self) -> Dict: ...
   ```

2. Implement `LocalEmbeddingProvider`
   - Use sentence-transformers
   - Load model on startup
   - Cache embeddings (LRU cache)
   - Batch processing
   - Tests

**Day 11: API Provider**

3. Implement `APIEmbeddingProvider`
   - HTTP calls to external API
   - Retry logic with exponential backoff
   - Rate limiting
   - Error handling
   - Tests (mock HTTP)

4. Implement `EmbeddingFactory`
   - Create provider based on config
   - Validate configuration
   - Tests

**Deliverable:** Embedding service working with both providers

---

### Phase 4: API Layer (Day 12-14)

**Day 12: Core API Structure**

1. Create FastAPI app in `src/api/main.py`
   - Lifespan events (startup/shutdown)
   - CORS middleware
   - Exception handlers
   - Health check endpoint
   - Metrics endpoint

2. Implement authentication middleware
   - `src/api/middleware/auth.py`
   - API key validation
   - Constant-time comparison
   - 401 errors
   - Tests

3. Implement logging middleware
   - Request/response logging
   - Duration tracking
   - Request ID generation
   - Tests

**Day 13: Memory Endpoints**

4. Implement POST `/memories`
   - Request validation (Pydantic)
   - Generate embedding if needed
   - Route to correct adapter
   - Store memory
   - Return memory_id
   - Error handling
   - Tests

5. Implement GET `/memories`
   - Query parameter validation
   - Route to correct adapter
   - Retrieve memories
   - Format response
   - Tests

6. Implement GET `/memories/{id}`
   - ID validation
   - Namespace check
   - Get from adapter
   - 404 if not found
   - Tests

7. Implement DELETE `/memories/{id}`
   - ID validation
   - Namespace check
   - Delete from adapter
   - Return success
   - Tests

**Day 14: Storage Manager**

8. Implement `StorageManager` in `src/storage/manager.py`
   - Route requests to correct adapter
   - Handle adapter initialization
   - Dependency injection for FastAPI
   - Tests

**Deliverable:** Full API working with all endpoints

---

### Phase 5: Testing & Quality (Day 15-17)

**Day 15: Unit Test Coverage**

1. Audit test coverage
   ```bash
   pytest --cov=src --cov-report=html --cov-report=term
   ```

2. Fill gaps to reach 90%+
   - All error paths
   - All validation logic
   - All utilities
   - Edge cases

**Day 16: Integration Tests**

3. Write comprehensive integration tests
   - Test each adapter with real DB
   - Test API endpoints end-to-end
   - Test error scenarios
   - Test multi-tenant isolation

**Day 17: E2E Tests**

4. Write E2E tests with docker-compose
   - Full stack up
   - Test complete flows
   - Test performance (100 concurrent requests)
   - Test memory lifecycle
   - Test namespace isolation paranoidly

**Deliverable:** 90%+ coverage, all tests passing

---

### Phase 6: Deployment (Day 18-19)

**Day 18: Docker**

1. Write `docker/Dockerfile`
   - Multi-stage build
   - Non-root user
   - Health check
   - Optimized layers

2. Write `docker/docker-compose.yml`
   - All services (api, redis, qdrant, postgres)
   - Health checks
   - Volumes
   - Networks
   - Depends_on with conditions

3. Test deployment
   ```bash
   docker-compose up -d
   # Wait for healthy
   curl http://localhost:8000/health
   # Run API tests
   pytest tests/integration/
   ```

**Day 19: Observability**

4. Implement Prometheus metrics
   - Request metrics
   - Storage operation metrics
   - Embedding metrics
   - Connection pool metrics

5. Set up health checks
   - Liveness: API responds
   - Readiness: All backends connected
   - Startup: Embedding model loaded

6. Test monitoring
   - Scrape `/metrics`
   - Verify all metrics present
   - Test health endpoints

**Deliverable:** Production-ready Docker deployment

---

### Phase 7: Documentation & Polish (Day 20-21)

**Day 20: Documentation**

1. Write comprehensive README.md
   - What is Smrti
   - Quick start (docker-compose up)
   - Configuration options
   - API examples
   - Troubleshooting

2. Write API documentation
   - All endpoints documented
   - Request/response examples
   - Error codes explained
   - Authentication guide

3. Write architecture docs
   - Component diagram
   - Data flow
   - Extension points
   - Adding new memory types

4. Write contributing guide
   - Development setup
   - Running tests
   - Code style
   - PR process

**Day 21: Final Polish**

5. Code review
   - Run all linters (black, ruff, mypy)
   - Fix all warnings
   - Remove debug code
   - Clean up TODOs

6. Performance testing
   - Load test with 100 concurrent users
   - Measure p50, p95, p99 latencies
   - Optimize if needed
   - Document results

7. Security audit
   - Check SQL injection vectors
   - Verify namespace isolation
   - Test API key security
   - Audit logging (no PII)

**Deliverable:** Production-ready, documented system

---

## Code Examples & Patterns

### Storage Adapter Implementation Pattern

```python
from typing import Dict, List, Optional, Any
from uuid import UUID
import asyncpg
from src.core.logging import get_logger
from src.storage.protocol import StorageAdapter
from src.storage.exceptions import StorageError

logger = get_logger(__name__)

class PostgresEpisodicAdapter(StorageAdapter):
    """Storage adapter for episodic memories using PostgreSQL."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize adapter with connection pool.
        
        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool
    
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Dict[str, Any]
    ) -> UUID:
        """
        Store an episodic memory in PostgreSQL.
        
        Args:
            memory_id: Unique identifier
            namespace: Isolation namespace
            data: Memory data (must contain 'text' and 'event_type')
            embedding: Not used for episodic (can be None)
            metadata: Additional metadata
            
        Returns:
            memory_id of stored memory
            
        Raises:
            StorageError: If database operation fails
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO episodic_memories 
                    (memory_id, namespace, event_type, event_data, metadata, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    memory_id,
                    namespace,
                    data.get("event_type", "unknown"),
                    data,
                    metadata,
                    metadata.get("timestamp", "now()")
                )
            
            logger.info(
                "episodic_memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                event_type=data.get("event_type")
            )
            
            return memory_id
            
        except Exception as e:
            logger.error(
                "episodic_memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to store episodic memory: {e}") from e
    
    async def retrieve(
        self,
        namespace: str,
        query: Optional[str],
        filters: Optional[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieve episodic memories.
        
        Args:
            namespace: Isolation namespace
            query: Optional text search query
            filters: Optional metadata filters (e.g., {"event_type": "goal_completed"})
            limit: Maximum results
            
        Returns:
            List of memories with metadata
        """
        try:
            # Build query dynamically based on filters
            sql = """
                SELECT memory_id, namespace, event_type, event_data, 
                       metadata, timestamp, created_at
                FROM episodic_memories
                WHERE namespace = $1
            """
            params = [namespace]
            param_idx = 2
            
            # Add text search if query provided
            if query:
                sql += f" AND to_tsvector('english', event_data::text) @@ plainto_tsquery(${param_idx})"
                params.append(query)
                param_idx += 1
            
            # Add filters
            if filters:
                for key, value in filters.items():
                    if key == "event_type":
                        sql += f" AND event_type = ${param_idx}"
                        params.append(value)
                        param_idx += 1
                    # Add more filter types as needed
            
            sql += f" ORDER BY timestamp DESC LIMIT ${param_idx}"
            params.append(limit)
            
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(sql, *params)
            
            results = [
                {
                    "memory_id": str(row["memory_id"]),
                    "memory_type": "EPISODIC",
                    "namespace": row["namespace"],
                    "data": row["event_data"],
                    "metadata": {
                        **(row["metadata"] or {}),
                        "timestamp": row["timestamp"].timestamp(),
                        "event_type": row["event_type"]
                    },
                    "created_at": row["created_at"].isoformat()
                }
                for row in rows
            ]
            
            logger.debug(
                "episodic_memories_retrieved",
                namespace=namespace,
                query=query,
                count=len(results)
            )
            
            return results
            
        except Exception as e:
            logger.error(
                "episodic_memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve episodic memories: {e}") from e
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Get specific episodic memory by ID."""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT memory_id, namespace, event_type, event_data, 
                           metadata, timestamp, created_at
                    FROM episodic_memories
                    WHERE memory_id = $1 AND namespace = $2
                    """,
                    memory_id,
                    namespace
                )
            
            if not row:
                return None
            
            return {
                "memory_id": str(row["memory_id"]),
                "memory_type": "EPISODIC",
                "namespace": row["namespace"],
                "data": row["event_data"],
                "metadata": {
                    **(row["metadata"] or {}),
                    "timestamp": row["timestamp"].timestamp(),
                    "event_type": row["event_type"]
                },
                "created_at": row["created_at"].isoformat()
            }
            
        except Exception as e:
            logger.error(
                "episodic_memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get episodic memory: {e}") from e
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """Delete an episodic memory."""
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(
                    """
                    DELETE FROM episodic_memories
                    WHERE memory_id = $1 AND namespace = $2
                    """,
                    memory_id,
                    namespace
                )
            
            # Extract number of rows deleted from result
            deleted = result.split()[-1] == "1"
            
            if deleted:
                logger.info(
                    "episodic_memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
            
            return deleted
            
        except Exception as e:
            logger.error(
                "episodic_memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete episodic memory: {e}") from e
    
    async def health_check(self) -> Dict[str, Any]:
        """Check PostgreSQL connection health."""
        try:
            async with self.pool.acquire() as conn:
                version = await conn.fetchval("SELECT version()")
                count = await conn.fetchval("SELECT COUNT(*) FROM episodic_memories")
            
            return {
                "status": "connected",
                "version": version.split()[1],  # Extract version number
                "memory_count": count
            }
        except Exception as e:
            logger.error("postgres_health_check_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
```

### API Endpoint Pattern

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID
from typing import Optional, Dict, Any
from src.api.models.requests import StoreMemoryRequest
from src.api.models.responses import StoreMemoryResponse, RetrieveMemoriesResponse
from src.api.middleware.auth import verify_api_key
from src.storage.manager import StorageManager
from src.core.logging import get_logger
from src.core.types import MemoryType

router = APIRouter(prefix="/memories", tags=["memories"])
logger = get_logger(__name__)

@router.post("", response_model=StoreMemoryResponse, status_code=201)
async def store_memory(
    request: StoreMemoryRequest,
    storage: StorageManager = Depends(get_storage_manager),
    api_key: str = Depends(verify_api_key)
):
    """
    Store a memory in the specified tier.
    
    Args:
        request: Memory data and metadata
        storage: Storage manager (injected)
        api_key: Validated API key (injected)
        
    Returns:
        Stored memory metadata
        
    Raises:
        HTTPException: 400 for validation errors, 500 for storage errors
    """
    try:
        # Validate memory type
        try:
            memory_type = MemoryType(request.memory_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": f"Invalid memory_type: {request.memory_type}",
                    "field": "memory_type"
                }
            )
        
        # Store memory
        memory_id = await storage.store(
            memory_type=memory_type,
            namespace=request.namespace,
            data=request.data,
            metadata=request.metadata or {}
        )
        
        logger.info(
            "memory_stored_via_api",
            memory_id=str(memory_id),
            memory_type=request.memory_type,
            namespace=request.namespace
        )
        
        return StoreMemoryResponse(
            memory_id=memory_id,
            memory_type=request.memory_type,
            namespace=request.namespace,
            stored_at=datetime.utcnow(),
            embedding_generated=memory_type == MemoryType.LONG_TERM
        )
        
    except StorageError as e:
        logger.error(
            "api_store_memory_failed",
            memory_type=request.memory_type,
            namespace=request.namespace,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "storage_error",
                "message": "Failed to store memory"
            }
        )

@router.get("", response_model=RetrieveMemoriesResponse)
async def retrieve_memories(
    memory_type: str = Query(..., description="Memory tier to search"),
    namespace: str = Query(..., description="Isolation namespace"),
    query: Optional[str] = Query(None, description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum results"),
    filters: Optional[str] = Query(None, description="JSON metadata filters"),
    storage: StorageManager = Depends(get_storage_manager),
    api_key: str = Depends(verify_api_key)
):
    """Retrieve memories matching query and filters."""
    try:
        # Validate memory type
        try:
            mem_type = MemoryType(memory_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "validation_error",
                    "message": f"Invalid memory_type: {memory_type}",
                    "field": "memory_type"
                }
            )
        
        # Parse filters if provided
        filter_dict = None
        if filters:
            try:
                filter_dict = json.loads(filters)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "validation_error",
                        "message": "Invalid JSON in filters parameter",
                        "field": "filters"
                    }
                )
        
        # Retrieve memories
        results = await storage.retrieve(
            memory_type=mem_type,
            namespace=namespace,
            query=query,
            filters=filter_dict,
            limit=limit
        )
        
        logger.debug(
            "memories_retrieved_via_api",
            memory_type=memory_type,
            namespace=namespace,
            count=len(results)
        )
        
        return RetrieveMemoriesResponse(
            results=results,
            total=len(results),
            limit=limit,
            query=query
        )
        
    except StorageError as e:
        logger.error(
            "api_retrieve_memories_failed",
            memory_type=memory_type,
            namespace=namespace,
            error=str(e)
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "storage_error",
                "message": "Failed to retrieve memories"
            }
        )
```

### Test Pattern

```python
import pytest
import asyncio
from uuid import uuid4
from src.storage.adapters.postgres_episodic import PostgresEpisodicAdapter
from src.storage.exceptions import StorageError

@pytest.mark.asyncio
class TestPostgresEpisodicAdapter:
    """Test suite for PostgreSQL episodic memory adapter."""
    
    async def test_store_and_retrieve(self, pg_pool):
        """Test basic store and retrieve flow."""
        adapter = PostgresEpisodicAdapter(pg_pool)
        
        # Store memory
        memory_id = uuid4()
        namespace = "test:user:123"
        data = {
            "text": "User completed workout goal",
            "event_type": "goal_completed"
        }
        metadata = {"impact": "high"}
        
        result = await adapter.store(
            memory_id=memory_id,
            namespace=namespace,
            data=data,
            embedding=None,
            metadata=metadata
        )
        
        assert result == memory_id
        
        # Retrieve by query
        results = await adapter.retrieve(
            namespace=namespace,
            query="workout",
            filters=None,
            limit=10
        )
        
        assert len(results) == 1
        assert results[0]["memory_id"] == str(memory_id)
        assert results[0]["data"]["event_type"] == "goal_completed"
        assert results[0]["metadata"]["impact"] == "high"
    
    async def test_namespace_isolation(self, pg_pool):
        """Test that namespaces are isolated."""
        adapter = PostgresEpisodicAdapter(pg_pool)
        
        # Store in namespace A
        await adapter.store(
            memory_id=uuid4(),
            namespace="tenant:1:user:a",
            data={"text": "Secret A", "event_type": "action"},
            embedding=None,
            metadata={}
        )
        
        # Store in namespace B
        await adapter.store(
            memory_id=uuid4(),
            namespace="tenant:1:user:b",
            data={"text": "Secret B", "event_type": "action"},
            embedding=None,
            metadata={}
        )
        
        # Retrieve from namespace A - should only see A
        results_a = await adapter.retrieve(
            namespace="tenant:1:user:a",
            query=None,
            filters=None,
            limit=100
        )
        
        assert all("Secret A" in r["data"]["text"] for r in results_a)
        assert not any("Secret B" in r["data"]["text"] for r in results_a)
    
    async def test_event_type_filtering(self, pg_pool):
        """Test filtering by event type."""
        adapter = PostgresEpisodicAdapter(pg_pool)
        namespace = "test:filters"
        
        # Store different event types
        await adapter.store(
            uuid4(), namespace,
            {"text": "Goal completed", "event_type": "goal_completed"},
            None, {}
        )
        await adapter.store(
            uuid4(), namespace,
            {"text": "Goal created", "event_type": "goal_created"},
            None, {}
        )
        
        # Filter for completed only
        results = await adapter.retrieve(
            namespace=namespace,
            query=None,
            filters={"event_type": "goal_completed"},
            limit=10
        )
        
        assert len(results) == 1
        assert results[0]["metadata"]["event_type"] == "goal_completed"
    
    async def test_delete(self, pg_pool):
        """Test memory deletion."""
        adapter = PostgresEpisodicAdapter(pg_pool)
        
        # Store
        memory_id = uuid4()
        namespace = "test:delete"
        await adapter.store(
            memory_id, namespace,
            {"text": "To be deleted", "event_type": "test"},
            None, {}
        )
        
        # Verify exists
        result = await adapter.get(memory_id, namespace)
        assert result is not None
        
        # Delete
        deleted = await adapter.delete(memory_id, namespace)
        assert deleted is True
        
        # Verify gone
        result = await adapter.get(memory_id, namespace)
        assert result is None
        
        # Delete again should return False
        deleted = await adapter.delete(memory_id, namespace)
        assert deleted is False
    
    async def test_health_check(self, pg_pool):
        """Test health check returns status."""
        adapter = PostgresEpisodicAdapter(pg_pool)
        
        health = await adapter.health_check()
        
        assert health["status"] == "connected"
        assert "version" in health
        assert "memory_count" in health
```

---

## Common Pitfalls to Avoid

### 1. Not Testing Multi-Tenancy
```python
# Bad - test only finds YOUR data
results = await storage.retrieve(namespace="user:123", query="test")
assert len(results) > 0

# Good - verify isolation
await store(namespace="user:123", text="Secret 123")
await store(namespace="user:456", text="Secret 456")

results_123 = await retrieve(namespace="user:123")
results_456 = await retrieve(namespace="user:456")

# Verify user 123 can't see user 456's data
assert not any("Secret 456" in r["data"]["text"] for r in results_123)
assert not any("Secret 123" in r["data"]["text"] for r in results_456)
```

### 2. Hardcoding Configuration
```python
# Bad
REDIS_URL = "redis://localhost:6379"

# Good
from src.core.config import settings
redis_url = settings.redis_url
```

### 3. Missing Error Context
```python
# Bad
try:
    await storage.store(...)
except Exception:
    raise StorageError("Storage failed")

# Good
try:
    await storage.store(...)
except Exception as e:
    logger.error(
        "storage_operation_failed",
        memory_id=str(memory_id),
        namespace=namespace,
        error=str(e),
        exc_info=True
    )
    raise StorageError(f"Failed to store memory {memory_id}: {e}") from e
```

### 4. Blocking I/O in Async Functions
```python
# Bad
async def embed(text: str):
    return model.encode(text)  # Blocking!

# Good
async def embed(text: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, model.encode, text)
```

### 5. Not Cleaning Up Test Data
```python
# Bad - test data leaks to other tests
@pytest.mark.asyncio
async def test_store():
    await storage.store(namespace="test", ...)

# Good - cleanup after each test
@pytest.mark.asyncio
async def test_store(pg_pool):
    try:
        await storage.store(namespace="test", ...)
        # assertions
    finally:
        await pg_pool.execute("DELETE FROM episodic_memories WHERE namespace = 'test'")

# Best - use fixtures with automatic cleanup
@pytest.fixture
async def clean_db(pg_pool):
    yield
    await pg_pool.execute("TRUNCATE episodic_memories, semantic_memories")
```

---

## Success Criteria Checklist

Before declaring "done", verify ALL of these:

### Functionality
- [ ] All 5 memory types store and retrieve correctly
- [ ] Embeddings generated for LONG_TERM memories
- [ ] Both local and API embedding providers work
- [ ] Multi-tenant isolation verified by tests
- [ ] API authentication working
- [ ] All endpoints return correct responses
- [ ] Error handling works for all failure modes

### Code Quality
- [ ] No linter errors (black, ruff, mypy all pass)
- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] No commented-out code
- [ ] No debug print statements
- [ ] No hardcoded values
- [ ] All TODOs resolved or documented

### Testing
- [ ] Overall test coverage ≥ 90%
- [ ] All adapters have unit tests
- [ ] All API endpoints have integration tests
- [ ] Multi-tenant isolation has E2E tests
- [ ] Error paths are tested
- [ ] Performance tests pass (100 concurrent requests)
- [ ] All tests pass in CI

### Deployment
- [ ] Docker build succeeds
- [ ] docker-compose up works
- [ ] All services become healthy
- [ ] Health check endpoint returns 200
- [ ] Metrics endpoint returns data
- [ ] Can store and retrieve via API in Docker

### Documentation
- [ ] README has quick start guide
- [ ] API endpoints documented
- [ ] Configuration options explained
- [ ] Architecture documented
- [ ] Troubleshooting guide exists
- [ ] Examples provided

### Security
- [ ] SQL injection tests pass
- [ ] API key validation works
- [ ] Namespace isolation verified
- [ ] No secrets in logs
- [ ] Input validation comprehensive

---

## When You Need Help

**Ask questions immediately if:**
- PRD is unclear or contradictory
- You discover a missing requirement
- You're stuck on a technical decision
- You find a better way to implement something
- Tests reveal a design flaw

**Don't ask for:**
- Permission to follow the PRD (just do it)
- Validation of correct implementations (tests prove correctness)
- Approval for code style (follow the standards)

---

## Final Reminders

1. **Read the PRD thoroughly before starting**
2. **Write tests first, then implementation**
3. **Commit frequently with clear messages**
4. **No shortcuts on quality - this is production code**
5. **Document as you go, not at the end**
6. **Test multi-tenancy paranoidly**
7. **Ask questions when unclear**
8. **Ship a complete, working system**

You have 21 days. The timeline is aggressive but achievable if you stay focused.

Build something we can be proud of. Build something that scales. Build something that works.

**Now go build Smrti v2.0.** 🚀

---

**END OF MASTER PROMPT**
