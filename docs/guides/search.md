# Search Guide

smrti provides three search modes -- vector, text, and hybrid -- each suited to different retrieval needs. This guide covers every search capability, from basic queries to advanced filtering and tuning.

## Search Modes

### Vector Search

Vector search finds nodes by semantic similarity. Your query is embedded into a vector and compared against stored node embeddings using cosine distance (or L2/inner product, depending on your config).

**When to use:** The query is conceptual or paraphrased. You want "things that mean the same thing" regardless of exact wording. For example, searching "annual compensation" should find nodes about "salary" and "yearly pay".

```python
result = await memory.search("annual compensation", mode="vector")
```

Under the hood, this runs a pgvector cosine similarity query:

```sql
SELECT n.*, 1 - (ne.embedding <=> query_vector) AS similarity
FROM nodes n
JOIN node_embeddings ne ON ne.node_id = n.id
WHERE n.is_retracted = FALSE
ORDER BY ne.embedding <=> query_vector
LIMIT 10
```

### Text Search

Text search uses PostgreSQL full-text search (tsvector/tsquery) with a trigram fallback. It finds nodes containing the words in your query, with stemming and ranking.

**When to use:** You need exact or near-exact keyword matches. The user typed a specific name, ID, or technical term that must appear literally.

```python
result = await memory.search("Alice Johnson", mode="text")
```

**How the fallback works:** The primary search uses `plainto_tsquery` against each node's `search_vector` column. If that returns fewer results than the requested limit, smrti automatically falls back to trigram similarity (`pg_trgm`) to catch partial matches, typos, and substrings. Results from the trigram fallback are appended (duplicates excluded).

### Hybrid Search (Default)

Hybrid mode runs both vector and text searches, then fuses their results using Reciprocal Rank Fusion (RRF). This is the default mode and the best general-purpose choice.

**When to use:** Almost always. Hybrid captures both semantic meaning and keyword relevance. It is the default for a reason.

```python
# These are equivalent -- hybrid is the default
result = await memory.search("project deadlines Q3")
result = await memory.search("project deadlines Q3", mode="hybrid")
```

#### How RRF Works

Reciprocal Rank Fusion combines ranked lists from different search methods without needing to normalize their scores (which are on different scales).

For each result, the RRF score is:

```
rrf_score = 1/(k + vector_rank) + 1/(k + text_rank)
```

Where `k` is the RRF constant (default 60). If a result appears in only one list, the missing term contributes 0.

**Why this works better than either alone:**
- A node ranked #2 by vector and #5 by text gets a high combined score
- A node ranked #1 by vector but absent from text results still scores well
- The `k` constant controls how much rank differences matter -- higher `k` makes the fusion more conservative (less difference between rank 1 and rank 10)

Both search modes independently fetch up to `hybrid_candidate_pool` candidates (default 100), then RRF merges and re-ranks them down to your `limit`.

## Filtering Results

### Edge-Based Filters

The `edge_type` and `edge_target` parameters filter search results to nodes that have specific relationships. These are flat string parameters designed for LLM tool calling.

**Find people who work at a specific company:**

```python
result = await memory.search(
    "senior engineer",
    edge_type="WORKS_AT",
    edge_target="<company-node-id>",
)
```

This returns only nodes that have an outgoing `WORKS_AT` edge pointing to the specified company node.

**Find all nodes with a specific edge type (no specific target):**

```python
result = await memory.search(
    "machine learning",
    edge_type="AUTHORED",
)
```

This returns nodes that have any outgoing `AUTHORED` edge, regardless of target.

Under the hood, these parameters are translated to `EdgeFilter` objects that generate `EXISTS` subqueries:

```sql
AND EXISTS (
    SELECT 1 FROM edges e_filter
    WHERE e_filter.source_node_id = n.id
      AND e_filter.edge_type = 'WORKS_AT'
      AND e_filter.is_retracted = FALSE
      AND e_filter.valid_from <= NOW()
      AND (e_filter.valid_to IS NULL OR e_filter.valid_to >= NOW())
      AND e_filter.target_node_id = '<target-uuid>'
)
```

### Metadata Filtering

The `filters` parameter matches against JSONB metadata stored on nodes. It uses PostgreSQL's containment operator (`@>`), so the filter dict must be a subset of the node's metadata.

```python
# Find nodes tagged with a specific department
result = await memory.search(
    "quarterly report",
    filters={"department": "engineering"},
)

# Multiple filter keys (all must match)
result = await memory.search(
    "budget proposal",
    filters={"department": "finance", "status": "approved"},
)
```

### Time-Range Filtering

Use `after` and `before` to restrict results to nodes created within a time window. Values are ISO 8601 date strings.

```python
# Nodes created in March 2026
result = await memory.search(
    "project update",
    after="2026-03-01",
    before="2026-04-01",
)

# Everything since last week
result = await memory.search(
    "meeting notes",
    after="2026-03-28",
)
```

### Node Type Filtering

Restrict results to a specific node type:

```python
result = await memory.search("machine learning", node_type="person")
```

### Combining Filters

All filters compose. Use them together for precise retrieval:

```python
result = await memory.search(
    "budget concerns",
    mode="hybrid",
    node_type="document",
    edge_type="AUTHORED_BY",
    filters={"status": "draft"},
    after="2026-01-01",
    limit=5,
    min_similarity=0.3,
)
```

## Multi-Namespace Search

Pass a comma-separated string to search across multiple namespaces:

```python
# Search in one namespace
result = await memory.search("project alpha", namespace="team:frontend")

# Search across multiple namespaces
result = await memory.search(
    "project alpha",
    namespace="team:frontend,team:backend,shared",
)
```

If `namespace` is omitted, the search uses `config.default_namespace`.

## The `_meta` Return Format

Every search result includes a `_meta` key with operational metadata:

```python
result = await memory.search("quarterly results", mode="hybrid")

print(result["_meta"])
# {
#     "search_mode": "hybrid",
#     "search_modes_used": ["vector", "text"],
#     "namespace": ["default"],
#     "total_candidates": 47,
#     "duration_ms": 12.3,
#     "rrf_k": 60,
#     "model_name": "default",
# }
```

| Field | Description |
|-------|-------------|
| `search_mode` | The mode you requested |
| `search_modes_used` | Which modes actually contributed results. In hybrid mode, if text search found nothing, this might be `["vector"]` only |
| `namespace` | List of namespaces that were searched |
| `total_candidates` | How many candidates were considered before applying the final limit |
| `returned` | Number of results in the `results` list |
| `duration_ms` | Wall-clock time for the search operation |
| `rrf_k` | The RRF constant used (only present for hybrid mode) |
| `model_name` | Which embedding model was used for vector search |

Each result in the `results` list contains:

```python
{
    "node_id": "abc-123-...",
    "content": "Alice Johnson is a senior engineer at Acme Corp",
    "node_type": "person",
    "similarity": 0.87,
    "metadata": {"department": "engineering"},
    "edges": [...]  # present in search(), not in find_similar()
}
```

## Convenience Method: find_similar

`find_similar()` is a shortcut for pure vector search when you just want semantically similar nodes:

```python
result = await memory.find_similar(
    "distributed systems architecture",
    namespace="knowledge-base",
    node_type="concept",
    limit=5,
    min_similarity=0.5,
)
```

This is equivalent to `search(..., mode="vector")` but with a simpler return format (no edges, no RRF metadata).

## Configuring Search Behavior

All search defaults live in `SmrtiConfig`. You can tune them at initialization:

```python
from smrti import Memory, SmrtiConfig

config = SmrtiConfig(
    dsn="postgresql://localhost:5432/mydb",
    embedding_provider=my_embedder,

    # Default number of results
    search_limit=10,

    # Minimum similarity threshold (0.0 = return everything)
    min_similarity=0.0,

    # Default search mode: "vector", "text", or "hybrid"
    search_mode="hybrid",

    # RRF constant -- higher = smoother rank fusion
    rrf_k=60,

    # Candidates fetched per mode before RRF fusion
    hybrid_candidate_pool=100,

    # PostgreSQL text search language for stemming/ranking
    search_language="english",
)

memory = Memory(config)
```

### search_limit

How many results to return by default. Override per-call with the `limit` parameter.

### min_similarity

Minimum cosine similarity for vector results. Set to 0.0 (default) to return all results regardless of similarity. Raise to 0.3-0.5 to filter out low-quality matches.

### rrf_k

The constant in the RRF formula `1/(k + rank)`. Default is 60 (a standard value from the original RRF paper). Lower values give more weight to top-ranked results; higher values spread weight more evenly across ranks.

### hybrid_candidate_pool

How many candidates each search mode fetches before RRF fusion. Must be >= `search_limit`. Higher values find more diverse results but cost more in query time. Default 100 works well for most cases.

### search_language

The PostgreSQL text search configuration used for stemming and query parsing. Default is `"english"`. Change to match your content language:

```python
config = SmrtiConfig(
    # ...
    search_language="spanish",  # or "french", "german", "simple", etc.
)
```

Note: The `search_vector` column is always indexed with the `'simple'` configuration (language-agnostic tokenization), so switching languages does not require re-indexing. The `search_language` setting only affects how queries are parsed and ranked at search time.

## Text Search Internals

Understanding the two-tier text search helps you debug empty results:

1. **tsvector (primary):** Uses `plainto_tsquery(search_language, query)` against the `search_vector` GIN index. Fast, supports stemming ("running" matches "run"), but requires at least one token match.

2. **Trigram fallback (secondary):** If tsvector returns fewer results than the limit, smrti queries `similarity(content, query)` using the `pg_trgm` GIN index. This catches typos, partial words, and substrings. Results already found by tsvector are excluded.

The fallback is automatic and transparent. You can see which modes contributed results in `_meta["search_modes_used"]`.

## Examples

### Basic semantic search

```python
result = await memory.search("people who know about Kubernetes")
for r in result["results"]:
    print(f"{r['node_type']}: {r['content']} (similarity: {r['similarity']:.2f})")
```

### Search with all filters

```python
result = await memory.search(
    "security vulnerabilities",
    namespace="project:alpha,project:beta",
    mode="hybrid",
    node_type="issue",
    edge_type="ASSIGNED_TO",
    edge_target="<user-node-id>",
    filters={"severity": "critical"},
    after="2026-01-01",
    before="2026-04-01",
    limit=20,
    min_similarity=0.4,
)

print(f"Found {len(result['results'])} results")
print(f"Searched {result['_meta']['total_candidates']} candidates")
print(f"Modes used: {result['_meta']['search_modes_used']}")
```

### Text-only search for exact names

```python
result = await memory.search(
    "CVE-2026-1234",
    mode="text",
    node_type="vulnerability",
)
```

### Find similar and then traverse

```python
# Find semantically similar nodes, then explore their neighborhood
similar = await memory.find_similar("distributed consensus algorithms")
if similar["results"]:
    top_node = similar["results"][0]["node_id"]
    graph = await memory.traverse(top_node, depth=2, edge_types="RELATES_TO,DEPENDS_ON")
```
