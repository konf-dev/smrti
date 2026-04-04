# Search guide

## Overview

The `search()` method queries the knowledge graph across one or more namespaces. It supports three modes -- `vector`, `text`, and `hybrid` -- and returns results ranked by relevance.

**smrti does not compute embeddings.** You must embed your query text externally (using the same model you used for your nodes) and pass the resulting vector to `search()`.

## Basic usage

```python
from smrti import Memory

memory = Memory.connect("postgresql://user:pass@localhost:5432/myapp")

# Hybrid search (default) -- requires both query_vector and text_query
results = memory.search(
    query_vector=[0.12, -0.34, 0.56, ...],  # embed("software engineer") from your model
    text_query="software engineer",
)

for r in results["results"]:
    print(f"{r['node_type']}: {r['content']} (similarity={r['similarity']:.3f})")
```

## Search modes

### Vector

Uses pgvector HNSW index to find nodes whose embeddings are closest to `query_vector`.

```python
results = memory.search(
    query_vector=[0.12, -0.34, 0.56, ...],
    mode="vector",
)
```

Requires `query_vector`. Raises `ValueError` if not provided.

### Text

Uses PostgreSQL full-text search (`tsvector`/`tsquery`). If full-text search returns no results and `text_search_trigram_fallback` is enabled (the default), smrti falls back to trigram similarity matching.

```python
results = memory.search(
    text_query="software engineer Berlin",
    mode="text",
)
```

Requires `text_query`. Raises `ValueError` if not provided.

### Hybrid

Runs both vector and text search independently, then merges results using Reciprocal Rank Fusion (RRF). This typically gives the best results because it combines semantic similarity with lexical matching.

```python
results = memory.search(
    query_vector=[0.12, -0.34, 0.56, ...],
    text_query="software engineer",
    mode="hybrid",
)
```

Requires both `query_vector` and `text_query`. Raises `ValueError` if either is missing.

## Filtering

### By node type

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    node_type="person",
)
```

### By metadata

Uses PostgreSQL JSONB containment (`@>`). The filter dict must be a subset of the node's metadata.

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    metadata_filter={"department": "engineering", "level": "senior"},
)
```

### By edge

Find nodes that have a specific outgoing edge type:

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    edge_type="works_at",
)
```

Optionally filter to nodes connected to a specific target:

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    edge_type="works_at",
    edge_target="uuid-of-company-node",
)
```

### By time

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    after="2024-01-01",
    before="2024-12-31",
)
```

### Multiple namespaces

```python
results = memory.search(
    query_vector=vec,
    text_query="engineer",
    namespaces=["team_a", "team_b"],
)
```

## Controlling results

### Limit

```python
results = memory.search(query_vector=vec, text_query="engineer", limit=5)
```

Default: `search_limit` from config (10).

### Minimum similarity

```python
results = memory.search(query_vector=vec, text_query="engineer", min_similarity=0.75)
```

Default: `min_similarity` from config (0.0).

## Response structure

```python
{
    "results": [
        {
            "node_id": "abc-123",
            "content": "Alice is a software engineer in Berlin.",
            "node_type": "person",
            "similarity": 0.92,
            "matched_by": ["vector", "text"],
            "metadata": {"department": "engineering"},
        },
        ...
    ],
    "_meta": {
        "search_mode": "hybrid",
        "search_modes_used": ["vector", "text"],
        "namespace": ["default"],
        "returned": 3,
        "duration_ms": 12.5,
    }
}
```

The `matched_by` field on each result tells you which search mode(s) found that node. In hybrid mode, a node can appear in both vector and text results.

## Tuning hybrid search

Several config parameters control hybrid search behavior:

| Parameter | Default | Description |
|---|---|---|
| `rrf_k` | 60 | RRF smoothing constant. Higher values reduce the impact of rank differences. |
| `hybrid_candidate_pool` | 100 | Number of candidates fetched from each mode before fusion. |
| `text_search_trigram_fallback` | true | Fall back to trigram similarity when full-text search returns no results. |
| `search_language` | `"english"` | PostgreSQL text search configuration name. |

```python
memory = Memory.connect(
    "postgresql://localhost/myapp",
    rrf_k=40,
    hybrid_candidate_pool=200,
    text_search_trigram_fallback=False,
)
```
