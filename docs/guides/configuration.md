# Configuration Guide

Every behavior in smrti is controlled through `SmrtiConfig`. There are no magic numbers buried in the code -- every threshold, limit, and default is a config field you can tune.

`SmrtiConfig` is a Pydantic `BaseModel`. Fields are validated at construction time, so invalid values fail fast with clear error messages.

```python
from smrti import SmrtiConfig, Memory

config = SmrtiConfig(
    dsn="postgresql://user:pass@localhost:5432/mydb",
    embedding_provider=my_embedder,
    # ... all other fields have sensible defaults
)
memory = Memory(config)
```

## Required Fields

### dsn

| | |
|---|---|
| **Type** | `str` |
| **Default** | (none -- required) |
| **Validation** | Must start with `postgresql://` or `postgres://` |

PostgreSQL connection string. This is the only required string field.

**Why you'd change it:** You always set this. It points to your PostgreSQL instance.

```python
config = SmrtiConfig(
    dsn="postgresql://user:pass@localhost:5432/smrti_db",
    embedding_provider=embedder,
)
```

### embedding_provider

| | |
|---|---|
| **Type** | `EmbeddingProvider` |
| **Default** | (none -- required) |
| **Validation** | Must implement the `EmbeddingProvider` protocol (`embed()`, `model_name`, `dimensions`) |

The provider used to generate vector embeddings for node content. smrti ships two implementations:

```python
from smrti.providers import OllamaEmbedding, OpenAIEmbedding

# Local Ollama
embedder = OllamaEmbedding(model="nomic-embed-text")

# OpenAI-compatible API
embedder = OpenAIEmbedding(model="text-embedding-3-small", api_key="sk-...")
```

## Extraction Fields

These control the high-level `store()` pipeline that extracts entities and relationships from raw text using an LLM.

### llm_provider

| | |
|---|---|
| **Type** | `LLMProvider \| None` |
| **Default** | `None` |
| **Validation** | Must implement the `LLMProvider` protocol if provided |

The LLM used for entity extraction. Only required if you call `memory.store()`. If `None`, calling `store()` raises `ExtractionError`.

**Why you'd change it:** Set this when you want the high-level extraction pipeline. Leave it `None` if you only use low-level methods (`add_nodes`, `add_edges`).

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    llm_provider=my_llm,  # enables store()
)
```

### extraction_prompt

| | |
|---|---|
| **Type** | `str \| None` |
| **Default** | `None` (uses built-in prompt) |
| **Validation** | None |

Custom prompt template for the LLM extraction pipeline. The built-in prompt extracts general entities (people, organizations, concepts, events, locations) and relationships. Override this to specialize extraction for your domain.

**Why you'd change it:** Your domain has specific entity types (e.g., medical codes, legal citations) that the generic prompt misses.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    llm_provider=my_llm,
    extraction_prompt="""Extract medical entities (conditions, medications,
    procedures, providers) and their relationships from the following text.
    Respond with structured JSON matching the ExtractionResult schema.""",
)
```

### merge_threshold

| | |
|---|---|
| **Type** | `float` |
| **Default** | `0.85` |
| **Validation** | `0.0 <= merge_threshold <= 1.0` |

Cosine similarity threshold for entity deduplication during reconciliation. When a newly extracted entity has similarity >= this threshold to an existing node, they are treated as the same entity and the existing node is updated.

**Why you'd change it:** Lower it (e.g., 0.75) if you see too many duplicate nodes. Raise it (e.g., 0.95) if distinct entities are being incorrectly merged.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    merge_threshold=0.80,  # more aggressive dedup
)
```

### resolution_llm

| | |
|---|---|
| **Type** | `bool` |
| **Default** | `False` |
| **Validation** | None |

Whether to use an LLM call to resolve ambiguous matches during reconciliation. When enabled, candidates in the "gray zone" (similarity between `merge_threshold - 0.1` and `merge_threshold`) are sent to the LLM for a same-or-different decision.

**Why you'd change it:** Enable this for higher-quality dedup at the cost of additional LLM calls. Useful when your domain has many similar-but-distinct entities.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    llm_provider=my_llm,
    resolution_llm=True,
)
```

## Namespacing

### default_namespace

| | |
|---|---|
| **Type** | `str` |
| **Default** | `"default"` |
| **Validation** | Non-empty string |

The namespace used when no namespace is specified in API calls. Namespaces isolate data -- nodes and edges in different namespaces are invisible to each other (unless you explicitly search across namespaces).

**Why you'd change it:** Set a per-user or per-tenant namespace as the default so you don't have to pass it on every call.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    default_namespace=f"user:{user_id}",
)
```

## Connection Pool

### pool_min

| | |
|---|---|
| **Type** | `int` |
| **Default** | `2` |
| **Validation** | `>= 1` |

Minimum number of connections maintained in the asyncpg pool.

**Why you'd change it:** Increase for high-throughput applications to avoid connection creation latency. Decrease to `1` for lightweight single-user scripts.

### pool_max

| | |
|---|---|
| **Type** | `int` |
| **Default** | `10` |
| **Validation** | `>= pool_min` |

Maximum connections in the pool.

**Why you'd change it:** Increase for applications with many concurrent operations. Be mindful of your PostgreSQL `max_connections` setting.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    pool_min=5,
    pool_max=20,
)
```

## Search

### search_limit

| | |
|---|---|
| **Type** | `int` |
| **Default** | `10` |
| **Validation** | `>= 1` |

Default number of results returned by `search()` and `find_similar()`. Can be overridden per-call with the `limit` parameter.

**Why you'd change it:** Lower it for chat-style agents that only need a few results. Raise it for batch retrieval.

### min_similarity

| | |
|---|---|
| **Type** | `float` |
| **Default** | `0.0` |
| **Validation** | `0.0 <= min_similarity <= 1.0` |

Default minimum cosine similarity threshold for vector search results. `0.0` means return everything regardless of similarity. Set to `0.3`-`0.5` to filter out low-relevance results.

**Why you'd change it:** Raise it when you'd rather return fewer, higher-quality results than a full list padded with irrelevant matches.

### search_mode

| | |
|---|---|
| **Type** | `str` |
| **Default** | `"hybrid"` |
| **Validation** | Must be `"vector"`, `"text"`, or `"hybrid"` |

Default search mode. Can be overridden per-call.

**Why you'd change it:** Set to `"vector"` if your content is primarily semantic and keyword matching is unreliable. Set to `"text"` if you need exact keyword matching (e.g., code identifiers).

### search_language

| | |
|---|---|
| **Type** | `str` |
| **Default** | `"english"` |
| **Validation** | Must be a valid PostgreSQL text search configuration name |

PostgreSQL text search language for query parsing and ranking. The `search_vector` column is always indexed with `'simple'` (language-agnostic), so changing this does not require re-indexing -- it only affects how queries are parsed at search time.

**Why you'd change it:** Set to match your content language for proper stemming.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    search_language="german",
)
```

## Hybrid Search

### rrf_k

| | |
|---|---|
| **Type** | `int` |
| **Default** | `60` |
| **Validation** | `>= 1` |

The constant `k` in the Reciprocal Rank Fusion formula: `score = 1/(k + rank)`. Higher values smooth out rank differences (rank 1 and rank 10 score more similarly). Lower values amplify top-ranked results.

**Why you'd change it:** The default of 60 (from the original RRF paper) works well in most cases. Lower it to 20-30 if you want top results to dominate. Raise it to 100+ for more democratic fusion.

### hybrid_candidate_pool

| | |
|---|---|
| **Type** | `int` |
| **Default** | `100` |
| **Validation** | `>= search_limit` |

Number of candidates fetched from each search mode (vector and text) before RRF fusion. The final result is the top `search_limit` after fusion.

**Why you'd change it:** Increase for better recall at the cost of query time. If your dataset is small (< 1000 nodes), you can lower this.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    rrf_k=40,
    hybrid_candidate_pool=200,
)
```

## Traversal

### max_traversal_depth

| | |
|---|---|
| **Type** | `int` |
| **Default** | `5` |
| **Validation** | `>= 1` |

Maximum allowed depth for graph traversal (BFS hops). This is a safety limit -- the per-call `depth` parameter cannot exceed this value.

**Why you'd change it:** Lower it if your graph is densely connected and deep traversals are expensive. Raise it for sparse graphs where meaningful paths are longer.

### max_traversal_nodes

| | |
|---|---|
| **Type** | `int` |
| **Default** | `100` |
| **Validation** | `>= 1` |

Maximum nodes returned from a single traversal. Another safety limit to prevent runaway queries on dense graphs.

**Why you'd change it:** Raise it if you need to explore larger subgraphs. Lower it to keep response sizes small for LLM consumption.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    max_traversal_depth=3,
    max_traversal_nodes=50,
)
```

## Events

### max_events_export

| | |
|---|---|
| **Type** | `int` |
| **Default** | `10000` |
| **Validation** | `>= 1` |

Maximum events returned by `export_events()` in a single call. Paginate with `after_id` for larger exports.

**Why you'd change it:** Raise it for bulk exports. Lower it if you need to limit memory usage during export.

## pgvector

### hnsw_m

| | |
|---|---|
| **Type** | `int` |
| **Default** | `16` |
| **Validation** | `>= 2` |

HNSW index parameter: maximum number of bi-directional connections per node in the graph index. Higher values improve recall but increase index size and build time.

**Why you'd change it:** Increase to 32-64 for high-dimensional embeddings or when recall is critical. Lower to 8 for smaller datasets where build speed matters more.

### hnsw_ef_construction

| | |
|---|---|
| **Type** | `int` |
| **Default** | `64` |
| **Validation** | `>= 1` |

HNSW index parameter: size of the dynamic candidate list during index construction. Higher values produce better indexes but take longer to build.

**Why you'd change it:** Increase to 128-256 for production workloads where index quality matters. The default of 64 is fine for development and moderate datasets.

### distance_metric

| | |
|---|---|
| **Type** | `str` |
| **Default** | `"cosine"` |
| **Validation** | Must be `"cosine"`, `"l2"`, or `"inner_product"` |

Distance metric for vector search. Maps to pgvector operator classes:

| Value | pgvector ops |
|-------|-------------|
| `"cosine"` | `vector_cosine_ops` |
| `"l2"` | `vector_l2_ops` |
| `"inner_product"` | `vector_ip_ops` |

**Why you'd change it:** Most embedding models are designed for cosine similarity. Use `"inner_product"` if your embeddings are already normalized and you want slightly faster queries. Use `"l2"` if your embedding model documentation specifically recommends Euclidean distance.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    hnsw_m=32,
    hnsw_ef_construction=128,
    distance_metric="cosine",
)
```

## Embedding

### embedding_model

| | |
|---|---|
| **Type** | `str` |
| **Default** | `"default"` |
| **Validation** | None |

Key stored in the `node_embeddings.model_name` column. This identifies which embedding model produced each vector, enabling multi-model support in the same database.

**Why you'd change it:** Set this to match your embedding provider's model name for clarity. If you ever switch models, changing this value ensures old and new embeddings are stored separately, and HNSW indexes are created per model.

```python
config = SmrtiConfig(
    dsn="...",
    embedding_provider=embedder,
    embedding_model="text-embedding-3-small",
)
```

## Full Example

```python
from smrti import Memory, SmrtiConfig
from smrti.providers import OpenAIEmbedding

config = SmrtiConfig(
    # Required
    dsn="postgresql://user:pass@localhost:5432/smrti_db",
    embedding_provider=OpenAIEmbedding(model="text-embedding-3-small"),

    # Extraction
    llm_provider=my_llm,
    merge_threshold=0.85,
    resolution_llm=False,

    # Namespacing
    default_namespace="user:alice",

    # Connection Pool
    pool_min=2,
    pool_max=10,

    # Search
    search_limit=10,
    min_similarity=0.0,
    search_mode="hybrid",
    search_language="english",

    # Hybrid Search
    rrf_k=60,
    hybrid_candidate_pool=100,

    # Traversal
    max_traversal_depth=5,
    max_traversal_nodes=100,

    # Events
    max_events_export=10000,

    # pgvector
    hnsw_m=16,
    hnsw_ef_construction=64,
    distance_metric="cosine",

    # Embedding
    embedding_model="text-embedding-3-small",
)

memory = Memory(config)
await memory.connect()
```
