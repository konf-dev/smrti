# Configuration

## Passing config

All configuration is passed as keyword arguments to `Memory.connect()`. The only required parameter is the DSN (connection string).

```python
from smrti import Memory

# Minimal -- all defaults
memory = Memory.connect("postgresql://user:pass@localhost:5432/myapp")

# With overrides
memory = Memory.connect(
    "postgresql://user:pass@localhost:5432/myapp",
    default_namespace="my_agent",
    search_mode="hybrid",
    search_limit=20,
    min_similarity=0.5,
    pool_max=20,
)
```

## All configuration fields

### Required

| Field | Type | Description |
|---|---|---|
| `dsn` | string | PostgreSQL connection string. Must start with `postgresql://` or `postgres://`. |

### Namespacing

| Field | Type | Default | Description |
|---|---|---|---|
| `default_namespace` | string | `"default"` | Namespace used when none is specified in API calls. |

### Connection pool

| Field | Type | Default | Description |
|---|---|---|---|
| `pool_min` | int | 2 | Minimum connections in the pool. Must be >= 1. |
| `pool_max` | int | 10 | Maximum connections in the pool. Must be >= `pool_min`. |

### Search

| Field | Type | Default | Description |
|---|---|---|---|
| `search_limit` | int | 10 | Default number of results returned by `search()`. Must be >= 1. |
| `min_similarity` | float | 0.0 | Default minimum similarity threshold (0.0--1.0). |
| `search_mode` | string | `"hybrid"` | Default search mode: `"vector"`, `"text"`, or `"hybrid"`. |
| `search_language` | string | `"english"` | PostgreSQL text search configuration (used in `to_tsvector()` and `websearch_to_tsquery()`). |
| `rrf_k` | int | 60 | Reciprocal Rank Fusion constant. Higher values smooth rank differences. Must be >= 1. |
| `hybrid_candidate_pool` | int | 100 | Candidates fetched from each search mode before RRF fusion. Must be >= 10. |
| `text_search_trigram_fallback` | bool | true | Fall back to trigram similarity when full-text search returns no results. Disable for high-volume namespaces where trigram index cost is prohibitive. |

### Traversal

| Field | Type | Default | Description |
|---|---|---|---|
| `max_traversal_depth` | int | 5 | Maximum allowed depth for graph traversal. Must be >= 1. |
| `max_traversal_nodes` | int | 100 | Maximum nodes returned from a traversal. Must be >= 1. |

### Events

| Field | Type | Default | Description |
|---|---|---|---|
| `max_events_export` | int | 10000 | Maximum events returned by `export_events()` in a single call. |

### pgvector / HNSW index

| Field | Type | Default | Description |
|---|---|---|---|
| `hnsw_m` | int | 16 | HNSW index max connections per node. Higher = better recall, more memory. Must be >= 2. |
| `hnsw_ef_construction` | int | 64 | HNSW build-time search width. Higher = better recall, slower index build. Must be >= 16. |
| `distance_metric` | string | `"cosine"` | Vector distance metric: `"cosine"`, `"l2"`, or `"inner_product"`. |

### Embedding

| Field | Type | Default | Description |
|---|---|---|---|
| `embedding_model` | string | `"default"` | Default model name stored in `node_embeddings.model_name` when a node includes an embedding but no `model_name`. |

### Session state

| Field | Type | Default | Description |
|---|---|---|---|
| `session_state_default_ttl` | int or null | null | Default TTL (seconds) for session state entries. `null` means no expiry. Can be overridden per-call via `ttl_seconds`. |

## Validation

All config fields are validated at connect time. If any field is invalid, `Memory.connect()` raises a `ValueError` with a descriptive message.

```python
try:
    memory = Memory.connect(
        "postgresql://localhost/myapp",
        search_mode="invalid",
    )
except ValueError as e:
    print(e)  # "search_mode must be 'vector', 'text', or 'hybrid', got 'invalid'"
```

## Example: production setup

```python
memory = Memory.connect(
    "postgresql://prod-user:secret@db.example.com:5432/myapp",
    default_namespace="agent_v2",
    pool_min=5,
    pool_max=30,
    search_mode="hybrid",
    search_limit=15,
    min_similarity=0.4,
    rrf_k=60,
    hybrid_candidate_pool=150,
    hnsw_m=32,
    hnsw_ef_construction=128,
    distance_metric="cosine",
    embedding_model="text-embedding-3-small",
    session_state_default_ttl=3600,
)
```
