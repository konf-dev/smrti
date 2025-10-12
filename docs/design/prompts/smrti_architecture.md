# Smrti Architecture Documentation

**Version:** 2.0.0  
**Last Updated:** 2025-01-04  
**Purpose:** Technical architecture reference for developers extending Smrti

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architectural Principles](#architectural-principles)
3. [Component Architecture](#component-architecture)
4. [Data Flow](#data-flow)
5. [Storage Adapter Pattern](#storage-adapter-pattern)
6. [Extension Points](#extension-points)
7. [Performance Characteristics](#performance-characteristics)
8. [Security Model](#security-model)

---

## System Overview

Smrti is a multi-tier memory storage system designed for agentic AI applications. It provides specialized storage backends for five distinct memory types, each optimized for different access patterns and retention policies.

### Key Characteristics

- **Pluggable Architecture**: Swap storage backends without code changes
- **Multi-Tenant by Design**: Complete isolation between namespaces
- **Protocol-Based**: Clear contracts between components
- **Async-First**: Non-blocking I/O throughout
- **Observable**: Structured logs and Prometheus metrics

### Technology Stack

```
┌─────────────────────────────────────────────┐
│ Application Layer                           │
│ • FastAPI (async web framework)             │
│ • Uvicorn (ASGI server)                     │
│ • Pydantic (validation & serialization)     │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ Storage Layer                               │
│ • Redis (in-memory, TTL support)            │
│ • Qdrant (vector database)                  │
│ • PostgreSQL (relational, full-text search) │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ Supporting Services                         │
│ • sentence-transformers (local embeddings)  │
│ • structlog (structured logging)            │
│ • prometheus-client (metrics)               │
└─────────────────────────────────────────────┘
```

---

## Architectural Principles

### 1. Separation of Concerns

Each layer has a single, well-defined responsibility:

```
┌──────────────────────────────────────────────────┐
│ API Layer                                        │
│ Responsibility: HTTP interface, auth, validation │
│ Knows about: Request/response models, FastAPI    │
│ Doesn't know: Storage implementation details     │
└──────────────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Storage Manager                                  │
│ Responsibility: Route to correct adapter         │
│ Knows about: Memory types, adapter registry      │
│ Doesn't know: Database connection details        │
└──────────────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Storage Adapters                                 │
│ Responsibility: CRUD operations for one memory   │
│ Knows about: Specific database client            │
│ Doesn't know: Other adapters or API layer        │
└──────────────────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────┐
│ Database Clients                                 │
│ Responsibility: Connection management, queries   │
│ Knows about: Database protocol                   │
│ Doesn't know: Smrti concepts                     │
└──────────────────────────────────────────────────┘
```

### 2. Protocol-Based Design

All adapters implement the same protocol, enabling polymorphism:

```python
from typing import Protocol, List, Dict, Any, Optional
from uuid import UUID

class StorageAdapter(Protocol):
    """
    Contract that all storage adapters must implement.
    Enables swapping implementations without changing callers.
    """
    
    async def store(...) -> UUID: ...
    async def retrieve(...) -> List[Dict[str, Any]]: ...
    async def get(...) -> Optional[Dict[str, Any]]: ...
    async def delete(...) -> bool: ...
    async def health_check() -> Dict[str, Any]: ...
```

**Benefits:**
- ✅ Type-safe at compile time (mypy verification)
- ✅ Clear contract for implementers
- ✅ Easy to add new adapters
- ✅ Testable with mocks/fakes

### 3. Dependency Injection

Components receive dependencies via constructor, not global imports:

```python
# Good - dependencies injected
class StorageManager:
    def __init__(
        self,
        working_adapter: StorageAdapter,
        short_term_adapter: StorageAdapter,
        long_term_adapter: StorageAdapter,
        episodic_adapter: StorageAdapter,
        semantic_adapter: StorageAdapter,
        embedding_service: EmbeddingProvider
    ):
        self.adapters = {
            MemoryType.WORKING: working_adapter,
            MemoryType.SHORT_TERM: short_term_adapter,
            MemoryType.LONG_TERM: long_term_adapter,
            MemoryType.EPISODIC: episodic_adapter,
            MemoryType.SEMANTIC: semantic_adapter
        }
        self.embedding_service = embedding_service

# Bad - global imports
class StorageManager:
    def __init__(self):
        self.redis = Redis()  # Hard dependency!
        self.qdrant = QdrantClient()  # Can't test!
```

**Benefits:**
- ✅ Easy to test (inject mocks)
- ✅ Clear dependencies
- ✅ Flexible configuration
- ✅ No hidden globals

### 4. Fail Fast

Validation and configuration errors happen at startup, not runtime:

```python
class Settings(BaseSettings):
    redis_url: str  # Required - fails if not set
    qdrant_url: str
    postgres_url: str
    
    @validator('redis_url')
    def validate_redis_url(cls, v):
        if not v.startswith('redis://'):
            raise ValueError('redis_url must start with redis://')
        return v

# Application startup
async def startup():
    # All validation happens here
    settings = Settings()
    
    # All connections tested here
    redis = await create_redis_pool(settings.redis_url)
    await redis.ping()  # Fail if can't connect
    
    qdrant = QdrantClient(settings.qdrant_url)
    await qdrant.health_check()  # Fail if can't connect
    
    # If we get here, system is ready
```

---

## Component Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         External Clients                         │
│              (Sutra agents, custom apps, curl, etc.)            │
└─────────────────────────────────────────────────────────────────┘
                              ▼ HTTP
┌─────────────────────────────────────────────────────────────────┐
│                         API Gateway                              │
│                      (FastAPI + Uvicorn)                         │
│                                                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐   │
│  │ Auth Middleware│  │  CORS Middleware│  │ Logging Middle │   │
│  │ (API keys)     │  │                │  │   ware         │   │
│  └────────────────┘  └────────────────┘  └────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   Route Handlers                          │  │
│  │  • POST /memories       • GET /memories/{id}             │  │
│  │  • GET /memories        • DELETE /memories/{id}          │  │
│  │  • GET /health          • GET /metrics                   │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Storage Manager                             │
│          (Routes requests to appropriate adapter)                │
│                                                                  │
│  Memory Type Router:                                            │
│    WORKING     → RedisWorkingAdapter                            │
│    SHORT_TERM  → RedisShortTermAdapter                          │
│    LONG_TERM   → QdrantLongTermAdapter + Embedding             │
│    EPISODIC    → PostgresEpisodicAdapter                        │
│    SEMANTIC    → PostgresSemanticAdapter                        │
└─────────────────────────────────────────────────────────────────┘
         ▼                ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   Redis     │  │   Qdrant    │  │  Postgres   │  │  Embedding  │
│  Adapters   │  │   Adapter   │  │  Adapters   │  │   Service   │
│             │  │             │  │             │  │             │
│ • Working   │  │ • Vector    │  │ • Episodic  │  │ • Local     │
│ • ShortTerm │  │   search    │  │ • Semantic  │  │ • API       │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
      ▼                 ▼                 ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│    Redis    │  │   Qdrant    │  │ PostgreSQL  │  │sentence-    │
│  Database   │  │  Database   │  │  Database   │  │transformers │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

### Component Responsibilities

#### 1. API Layer (`src/api/`)

**Responsibilities:**
- Accept HTTP requests
- Authenticate via API keys
- Validate request payloads
- Serialize responses
- Handle errors gracefully
- Log requests/responses
- Expose metrics

**Key Files:**
- `main.py` - FastAPI app setup, lifespan, middleware
- `routes/memories.py` - CRUD endpoints for memories
- `routes/health.py` - Health check endpoint
- `routes/metrics.py` - Prometheus metrics endpoint
- `middleware/auth.py` - API key validation
- `middleware/logging.py` - Request/response logging
- `models/requests.py` - Pydantic request models
- `models/responses.py` - Pydantic response models

**Dependencies:**
- FastAPI, Uvicorn
- Pydantic for validation
- Storage Manager (injected)

#### 2. Storage Manager (`src/storage/manager.py`)

**Responsibilities:**
- Route storage requests to correct adapter
- Coordinate embedding generation for vector memories
- Provide unified interface to API layer
- Handle adapter lifecycle

**Key Logic:**
```python
async def store(
    self,
    memory_type: MemoryType,
    namespace: str,
    data: Dict[str, Any],
    metadata: Dict[str, Any]
) -> UUID:
    # Generate ID
    memory_id = uuid4()
    
    # Generate embedding if needed
    embedding = None
    if memory_type == MemoryType.LONG_TERM:
        embedding = await self.embedding_service.embed([data["text"]])
        embedding = embedding[0]
    
    # Route to correct adapter
    adapter = self.adapters[memory_type]
    await adapter.store(memory_id, namespace, data, embedding, metadata)
    
    return memory_id
```

#### 3. Storage Adapters (`src/storage/adapters/`)

**Responsibilities:**
- Implement CRUD operations for one memory type
- Handle database-specific logic
- Enforce namespace isolation
- Provide health checks

**Adapter Types:**

**RedisWorkingAdapter:**
- TTL: 300 seconds
- Key pattern: `working:{namespace}:{memory_id}`
- Retrieval: Recent N items by timestamp

**RedisShortTermAdapter:**
- TTL: 3600 seconds
- Key pattern: `short_term:{namespace}:{memory_id}`
- Retrieval: Sorted sets for time ordering

**QdrantLongTermAdapter:**
- No TTL (persistent)
- Collection per namespace prefix
- Retrieval: Vector similarity search

**PostgresEpisodicAdapter:**
- Table: `episodic_memories`
- Retrieval: Time-range queries, full-text search
- Indexes: timestamp, event_type, namespace

**PostgresSemanticAdapter:**
- Table: `semantic_memories`
- Retrieval: Entity lookup, relationship traversal
- Indexes: entities JSONB, relationships JSONB

#### 4. Embedding Service (`src/embedding/`)

**Responsibilities:**
- Generate vector embeddings from text
- Support multiple providers (local, API)
- Cache embeddings for performance
- Handle provider failures

**Providers:**

**LocalEmbeddingProvider:**
- Uses sentence-transformers
- Model loaded at startup
- CPU/GPU execution
- LRU cache for repeated texts

**APIEmbeddingProvider:**
- HTTP calls to external API
- Retry with exponential backoff
- Rate limiting
- Timeout handling

#### 5. Configuration (`src/core/config.py`)

**Responsibilities:**
- Load configuration from environment
- Validate settings at startup
- Provide type-safe access
- Support multiple environments (dev/prod)

---

## Data Flow

### Store Memory Flow

```
┌─────────┐
│  Client │
└────┬────┘
     │ POST /memories
     │ {memory_type, namespace, data, metadata}
     ▼
┌─────────────────────────────────────┐
│ API Layer                           │
│ 1. Validate API key                 │
│ 2. Validate request payload         │
│ 3. Parse memory_type enum           │
└────┬────────────────────────────────┘
     │ store(memory_type, namespace, data, metadata)
     ▼
┌─────────────────────────────────────┐
│ Storage Manager                     │
│ 1. Generate UUID                    │
│ 2. Generate embedding (if needed)   │
│ 3. Select adapter by memory_type    │
└────┬────────────────────────────────┘
     │ adapter.store(id, namespace, data, embedding, metadata)
     ▼
┌─────────────────────────────────────┐
│ Storage Adapter                     │
│ 1. Format data for backend          │
│ 2. Apply namespace prefix           │
│ 3. Execute database operation       │
│ 4. Log operation                    │
└────┬────────────────────────────────┘
     │ INSERT/SET/ADD
     ▼
┌─────────────────────────────────────┐
│ Database                            │
│ • Redis: SET with TTL               │
│ • Qdrant: Add vector to collection  │
│ • Postgres: INSERT into table       │
└────┬────────────────────────────────┘
     │ Success/Error
     ▼
┌─────────────────────────────────────┐
│ Response to Client                  │
│ 201 Created                         │
│ {memory_id, stored_at, ...}         │
└─────────────────────────────────────┘
```

### Retrieve Memories Flow

```
┌─────────┐
│  Client │
└────┬────┘
     │ GET /memories?memory_type=...&namespace=...&query=...
     ▼
┌─────────────────────────────────────┐
│ API Layer                           │
│ 1. Validate API key                 │
│ 2. Validate query parameters        │
│ 3. Parse filters JSON               │
└────┬────────────────────────────────┘
     │ retrieve(memory_type, namespace, query, filters, limit)
     ▼
┌─────────────────────────────────────┐
│ Storage Manager                     │
│ 1. Select adapter by memory_type    │
│ 2. Generate query embedding (if     │
│    vector search)                   │
└────┬────────────────────────────────┘
     │ adapter.retrieve(namespace, query, filters, limit)
     ▼
┌─────────────────────────────────────┐
│ Storage Adapter                     │
│ 1. Build database query             │
│ 2. Apply namespace filter           │
│ 3. Apply additional filters         │
│ 4. Execute search                   │
│ 5. Format results                   │
└────┬────────────────────────────────┘
     │ SELECT/SCAN/SEARCH
     ▼
┌─────────────────────────────────────┐
│ Database                            │
│ • Redis: SCAN pattern + sort        │
│ • Qdrant: Vector similarity search  │
│ • Postgres: SQL query with filters  │
└────┬────────────────────────────────┘
     │ Results
     ▼
┌─────────────────────────────────────┐
│ Response to Client                  │
│ 200 OK                              │
│ {results: [...], total, limit}      │
└─────────────────────────────────────┘
```

### Multi-Tenant Isolation Flow

Every operation enforces namespace isolation:

```
Request with namespace="tenant:123:user:456"
              ▼
┌──────────────────────────────────────────┐
│ Storage Adapter                          │
│                                          │
│ Redis:                                   │
│   key = f"{memory_type}:{namespace}:*"   │
│   → "working:tenant:123:user:456:*"      │
│                                          │
│ Qdrant:                                  │
│   filter = {"namespace": namespace}      │
│   → Only vectors with matching metadata  │
│                                          │
│ Postgres:                                │
│   WHERE namespace = $1                   │
│   → Query always filters by namespace    │
└──────────────────────────────────────────┘
              ▼
Only data for "tenant:123:user:456" returned
```

---

## Storage Adapter Pattern

### Protocol Definition

```python
from typing import Protocol, Dict, List, Optional, Any
from uuid import UUID

class StorageAdapter(Protocol):
    """
    Protocol that all storage adapters must implement.
    
    This defines the contract between the Storage Manager
    and the specific storage implementations.
    """
    
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Dict[str, Any]
    ) -> UUID:
        """
        Store a memory in the backend.
        
        Args:
            memory_id: Unique identifier (generated by Storage Manager)
            namespace: Isolation key (e.g., "tenant:123:user:456")
            data: Memory data (must contain 'text' field)
            embedding: Vector embedding (None if not applicable)
            metadata: Additional metadata (tags, timestamp, etc.)
            
        Returns:
            memory_id: Confirmation of stored ID
            
        Raises:
            StorageError: If storage operation fails
            
        Notes:
            - Must enforce namespace isolation
            - Must handle database-specific errors
            - Must log operation for observability
        """
        ...
    
    async def retrieve(
        self,
        namespace: str,
        query: Optional[str],
        filters: Optional[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Retrieve memories matching query and filters.
        
        Args:
            namespace: Isolation key (MUST filter results)
            query: Search query (semantic for vectors, keyword for text)
            filters: Metadata filters (e.g., {"event_type": "goal"})
            limit: Maximum results to return
            
        Returns:
            List of memories with relevance scores
            
        Format:
            [
                {
                    "memory_id": str,
                    "memory_type": str,
                    "namespace": str,
                    "data": dict,
                    "metadata": dict,
                    "created_at": str,
                    "relevance_score": float  # Optional
                },
                ...
            ]
            
        Notes:
            - MUST filter by namespace (no cross-tenant leakage)
            - Return empty list if no matches (don't raise error)
            - Results should be sorted (relevance or time)
        """
        ...
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific memory by ID.
        
        Args:
            memory_id: Memory identifier
            namespace: Isolation key (for authorization)
            
        Returns:
            Memory data or None if not found or wrong namespace
            
        Notes:
            - Must verify namespace matches (security)
            - Return None (don't raise) if not found
        """
        ...
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """
        Delete a memory.
        
        Args:
            memory_id: Memory identifier
            namespace: Isolation key (for authorization)
            
        Returns:
            True if deleted, False if not found
            
        Notes:
            - Must verify namespace matches
            - Idempotent (delete twice = no error)
        """
        ...
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check health of storage backend.
        
        Returns:
            Dictionary with status information:
            {
                "status": "connected" | "error",
                "latency_ms": float,  # Optional
                "error": str,  # If status == "error"
                ...  # Backend-specific info
            }
            
        Notes:
            - Should be fast (< 100ms)
            - Used by /health endpoint
            - Don't raise exceptions (return error status)
        """
        ...
```

### Adapter Implementation Template

```python
from typing import Dict, List, Optional, Any
from uuid import UUID
import asyncpg
from src.storage.protocol import StorageAdapter
from src.storage.exceptions import StorageError
from src.core.logging import get_logger

logger = get_logger(__name__)

class MyCustomAdapter(StorageAdapter):
    """
    Storage adapter for [MEMORY_TYPE] using [DATABASE].
    
    Characteristics:
    - Storage: [WHERE DATA IS STORED]
    - TTL: [EXPIRATION POLICY]
    - Retrieval: [HOW QUERIES WORK]
    """
    
    def __init__(self, db_client):
        """
        Initialize adapter with database client.
        
        Args:
            db_client: Database connection/pool/client
        """
        self.db = db_client
    
    async def store(
        self,
        memory_id: UUID,
        namespace: str,
        data: Dict[str, Any],
        embedding: Optional[List[float]],
        metadata: Dict[str, Any]
    ) -> UUID:
        """Store memory in [DATABASE]."""
        try:
            # 1. Format data for backend
            # 2. Apply namespace prefix/filter
            # 3. Execute store operation
            # 4. Log success
            
            logger.info(
                "memory_stored",
                memory_id=str(memory_id),
                namespace=namespace,
                adapter=self.__class__.__name__
            )
            
            return memory_id
            
        except Exception as e:
            logger.error(
                "memory_store_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e),
                exc_info=True
            )
            raise StorageError(f"Failed to store: {e}") from e
    
    async def retrieve(
        self,
        namespace: str,
        query: Optional[str],
        filters: Optional[Dict[str, Any]],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Retrieve memories from [DATABASE]."""
        try:
            # 1. Build query with namespace filter
            # 2. Add additional filters
            # 3. Execute search
            # 4. Format results
            # 5. Return (empty list if no results)
            
            logger.debug(
                "memories_retrieved",
                namespace=namespace,
                query=query,
                count=len(results)
            )
            
            return results
            
        except Exception as e:
            logger.error(
                "memory_retrieve_failed",
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to retrieve: {e}") from e
    
    async def get(
        self,
        memory_id: UUID,
        namespace: str
    ) -> Optional[Dict[str, Any]]:
        """Get specific memory by ID."""
        try:
            # 1. Query by ID AND namespace
            # 2. Return None if not found
            # 3. Format and return if found
            
            return result
            
        except Exception as e:
            logger.error(
                "memory_get_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to get: {e}") from e
    
    async def delete(
        self,
        memory_id: UUID,
        namespace: str
    ) -> bool:
        """Delete a memory."""
        try:
            # 1. Delete by ID AND namespace
            # 2. Return True if deleted
            # 3. Return False if not found
            
            if deleted:
                logger.info(
                    "memory_deleted",
                    memory_id=str(memory_id),
                    namespace=namespace
                )
            
            return deleted
            
        except Exception as e:
            logger.error(
                "memory_delete_failed",
                memory_id=str(memory_id),
                namespace=namespace,
                error=str(e)
            )
            raise StorageError(f"Failed to delete: {e}") from e
    
    async def health_check(self) -> Dict[str, Any]:
        """Check database connection health."""
        try:
            # 1. Ping/test connection
            # 2. Return status info
            
            return {
                "status": "connected",
                "backend": "[DATABASE_NAME]",
                "latency_ms": latency
            }
        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return {
                "status": "error",
                "error": str(e)
            }
```

---

## Extension Points

### Adding a New Memory Type

**Steps:**

1. **Add enum value** in `src/core/types.py`:
   ```python
   class MemoryType(str, Enum):
       WORKING = "WORKING"
       SHORT_TERM = "SHORT_TERM"
       LONG_TERM = "LONG_TERM"
       EPISODIC = "EPISODIC"
       SEMANTIC = "SEMANTIC"
       PROCEDURAL = "PROCEDURAL"  # New!
   ```

2. **Create adapter** in `src/storage/adapters/`:
   ```python
   # procedural_adapter.py
   class ProceduralMemoryAdapter(StorageAdapter):
       # Implement all protocol methods
       ...
   ```

3. **Register in Storage Manager**:
   ```python
   # src/storage/manager.py
   def __init__(self, ..., procedural_adapter: StorageAdapter):
       self.adapters = {
           ...
           MemoryType.PROCEDURAL: procedural_adapter
       }
   ```

4. **Add to dependency injection**:
   ```python
   # src/api/main.py
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # ... existing adapters ...
       procedural_adapter = ProceduralMemoryAdapter(...)
       
       storage_manager = StorageManager(
           ...,
           procedural_adapter=procedural_adapter
       )
   ```

5. **Write tests**:
   - Unit tests for adapter
   - Integration tests with real database
   - API endpoint tests

**No changes needed:**
- ❌ API endpoints (already support all memory types)
- ❌ Authentication
- ❌ Validation (enum automatically includes new type)

### Switching Database Backend

Example: Replace Qdrant with Pinecone for long-term memory.

**Steps:**

1. **Create new adapter**:
   ```python
   # src/storage/adapters/pinecone_long_term.py
   class PineconeLongTermAdapter(StorageAdapter):
       def __init__(self, pinecone_client):
           self.client = pinecone_client
       
       # Implement all protocol methods
       async def store(...): ...
       async def retrieve(...): ...
       # etc.
   ```

2. **Update configuration**:
   ```python
   # src/core/config.py
   class Settings(BaseSettings):
       # Add Pinecone config
       pinecone_api_key: str
       pinecone_environment: str
       pinecone_index: str
   ```

3. **Swap in dependency injection**:
   ```python
   # src/api/main.py
   @asynccontextmanager
   async def lifespan(app: FastAPI):
       # Old
       # qdrant = QdrantClient(...)
       # long_term_adapter = QdrantLongTermAdapter(qdrant)
       
       # New
       pinecone = PineconeClient(...)
       long_term_adapter = PineconeLongTermAdapter(pinecone)
       
       storage_manager = StorageManager(
           ...,
           long_term_adapter=long_term_adapter  # Same interface!
       )
   ```

4. **Test**:
   - Unit tests for new adapter
   - Integration tests
   - Verify no other changes needed

**No changes needed:**
- ❌ API layer
- ❌ Storage Manager
- ❌ Other adapters
- ❌ Embedding service

### Adding a New Embedding Provider

Example: Add Cohere embeddings.

**Steps:**

1. **Implement protocol**:
   ```python
   # src/embedding/providers/cohere.py
   from cohere import Client
   from src.embedding.protocol import EmbeddingProvider
   
   class CohereEmbeddingProvider(EmbeddingProvider):
       def __init__(self, api_key: str, model: str):
           self.client = Client(api_key)
           self.model = model
       
       async def embed(self, texts: List[str]) -> List[List[float]]:
           response = self.client.embed(
               texts=texts,
               model=self.model
           )
           return response.embeddings
       
       def dimension(self) -> int:
           return 1024  # Cohere embedding size
       
       async def health_check(self) -> Dict[str, Any]:
           # Test API connection
           ...
   ```

2. **Add to factory**:
   ```python
   # src/embedding/factory.py
   def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
       if settings.embedding_provider == "local":
           return LocalEmbeddingProvider(...)
       elif settings.embedding_provider == "api":
           return APIEmbeddingProvider(...)
       elif settings.embedding_provider == "cohere":
           return CohereEmbeddingProvider(...)  # New!
       else:
           raise ValueError(f"Unknown provider: {settings.embedding_provider}")
   ```

3. **Update config**:
   ```python
   class Settings(BaseSettings):
       embedding_provider: Literal["local", "api", "cohere"]
       
       # Cohere-specific
       cohere_api_key: Optional[str] = None
       cohere_model: str = "embed-english-v3.0"
   ```

4. **Test and use**:
   ```bash
   EMBEDDING_PROVIDER=cohere
   COHERE_API_KEY=your-key
   ```

---

## Performance Characteristics

### Latency Targets

| Operation | Target (p95) | Notes |
|-----------|-------------|-------|
| Store WORKING | < 10ms | In-memory Redis |
| Store SHORT_TERM | < 10ms | In-memory Redis |
| Store LONG_TERM | < 100ms | Includes embedding generation |
| Store EPISODIC | < 50ms | Postgres INSERT |
| Store SEMANTIC | < 50ms | Postgres INSERT with JSONB |
| Retrieve WORKING | < 5ms | Redis SCAN |
| Retrieve SHORT_TERM | < 10ms | Redis sorted set range |
| Retrieve LONG_TERM | < 200ms | Vector similarity search |
| Retrieve EPISODIC | < 50ms | Postgres full-text search |
| Retrieve SEMANTIC | < 100ms | Postgres JSONB queries |

### Throughput Targets

- **Concurrent requests**: 100 simultaneous
- **Stores per second**: 500+ (mixed types)
- **Retrievals per second**: 1000+ (mixed types)

### Scalability Considerations

**Vertical Scaling:**
- Redis: Limited by available RAM
- Qdrant: GPU for faster vector search
- Postgres: More CPU/RAM for complex queries

**Horizontal Scaling:**
- Redis: Cluster mode (shard by namespace prefix)
- Qdrant: Distributed collections
- Postgres: Read replicas for retrievals
- API servers: Stateless, add more instances

**Bottlenecks:**
- Embedding generation (CPU-bound)
- Vector search (memory-bound)
- Postgres full-text search (I/O-bound)

---

## Security Model

### Authentication

**API Key Validation:**
```python
# Constant-time comparison (prevent timing attacks)
import hmac

def verify_api_key(provided_key: str, valid_keys: List[str]) -> bool:
    for valid_key in valid_keys:
        if hmac.compare_digest(provided_key, valid_key):
            return True
    return False
```

**Key Storage:**
- Environment variable: `API_KEYS=key1,key2,key3`
- File: `/config/api_keys.txt` (one per line)
- Never in database or logs

### Authorization

**Namespace-Based:**
- Every operation requires `namespace` parameter
- Adapter MUST filter by namespace
- No cross-namespace access possible

**Enforcement:**
```python
# Every query includes namespace filter
SELECT * FROM memories WHERE namespace = $namespace  # ✓

# This would leak data
SELECT * FROM memories  # ✗ Never do this
```

### Input Validation

**Sanitization:**
- Namespace: Alphanumeric + `:` and `-` only
- Memory ID: Valid UUID v4
- Text: Max 50,000 characters
- Metadata: Max 10KB JSON

**SQL Injection Prevention:**
- Always use parameterized queries
- Never concatenate user input into SQL
- Validate inputs before queries

### Data Protection

**At Rest:**
- Database encryption (managed by provider)
- No plain-text API keys
- Embeddings not human-readable

**In Transit:**
- HTTPS for all API calls (production)
- TLS for database connections (production)

**In Logs:**
- No API keys
- No full memory content (PII risk)
- No embeddings (too large)

---

## Monitoring & Observability

### Health Checks

**Liveness:** Is the API responding?
```bash
GET /health
# Returns 200 if alive (even if backends down)
```

**Readiness:** Are backends connected?
```bash
GET /health
{
  "status": "healthy",
  "storage": {
    "redis": {"status": "connected"},
    "qdrant": {"status": "connected"},
    "postgres": {"status": "connected"}
  }
}
# Returns 503 if any backend unavailable
```

### Metrics

**Key Metrics to Monitor:**

1. **Request Rate**
   - `smrti_requests_total{endpoint, method, status}`
   - Alert if: Sudden drop (service down) or spike (attack)

2. **Latency**
   - `smrti_request_duration_seconds{endpoint}`
   - Alert if: p95 > 500ms

3. **Error Rate**
   - `smrti_requests_total{status="5xx"} / smrti_requests_total`
   - Alert if: > 1%

4. **Storage Operations**
   - `smrti_storage_operations_total{operation, memory_type, status}`
   - Alert if: High error rate for any type

5. **Connection Pools**
   - `smrti_redis_connections_active`
   - `smrti_postgres_connections_active`
   - Alert if: Near max pool size (contention)

### Logging

**Structured Format:**
```json
{
  "timestamp": "2025-01-04T12:30:00.123Z",
  "level": "INFO",
  "logger": "smrti.storage.adapters.postgres_episodic",
  "message": "memory_stored",
  "memory_id": "550e8400-e29b-41d4-a716-446655440000",
  "namespace": "tenant:123:user:456",
  "duration_ms": 45.2
}
```

**Log Aggregation:**
- Collect all container logs
- Index by timestamp, namespace, memory_id
- Retention: 30 days minimum

---

## Troubleshooting Guide

### Common Issues

**1. Slow Vector Search**
- **Symptom**: Long-term memory retrieval > 500ms
- **Cause**: Too many vectors in collection
- **Solution**: 
  - Partition collections by tenant
  - Add metadata filters to narrow search
  - Upgrade Qdrant instance (more RAM)

**2. Redis Memory Exhaustion**
- **Symptom**: `OOM` errors, evictions
- **Cause**: Too many working/short-term memories
- **Solution**:
  - Reduce TTLs
  - Implement maxmemory policy (allkeys-lru)
  - Add more Redis memory

**3. Postgres Connection Pool Exhausted**
- **Symptom**: `PoolTimeout` errors
- **Cause**: Slow queries holding connections
- **Solution**:
  - Increase pool size
  - Add query timeout
  - Optimize slow queries (EXPLAIN ANALYZE)
  - Add connection pooler (PgBouncer)

**4. Multi-Tenant Data Leakage**
- **Symptom**: Users seeing others' data
- **Cause**: Missing namespace filter in query
- **Solution**:
  - Audit all queries (search for WHERE clauses)
  - Add integration test for isolation
  - Code review all adapter implementations

---

## Future Considerations

### Potential Enhancements

1. **Batch Operations**
   - Store/retrieve multiple memories in one call
   - Reduces round-trips for bulk operations

2. **Memory Linking**
   - Reference relationships between memories
   - Useful for episodic chains, fact derivation

3. **Memory Versioning**
   - Update existing memory, keep history
   - Useful for evolving facts, goal tracking

4. **Consolidation Service**
   - Background jobs to move memories between tiers
   - Intelligent summarization with LLMs

5. **Caching Layer**
   - Cache frequent retrievals (e.g., user profile)
   - Invalidation on updates

6. **GraphQL API**
   - Alternative to REST
   - Better for complex queries

7. **Streaming**
   - WebSocket for real-time updates
   - Useful for proactive agents

---

## Appendix: Adapter Comparison

| Feature | Redis (Working) | Redis (Short) | Qdrant (Long) | Postgres (Episodic) | Postgres (Semantic) |
|---------|----------------|---------------|---------------|---------------------|---------------------|
| **Persistence** | Volatile (TTL) | Volatile (TTL) | Persistent | Persistent | Persistent |
| **Search Type** | Key pattern | Key pattern | Vector similarity | Full-text + SQL | JSONB queries |
| **TTL** | 5 min | 1 hour | None | None | None |
| **Best For** | Current context | Session summary | Semantic facts | Event timeline | Knowledge graph |
| **Query Speed** | < 5ms | < 10ms | < 200ms | < 50ms | < 100ms |
| **Scalability** | High (in-memory) | High (in-memory) | Medium (RAM-bound) | High (sharding) | High (sharding) |

---

**END OF ARCHITECTURE DOCUMENTATION**
