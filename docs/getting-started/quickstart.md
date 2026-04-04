# Quickstart

This guide walks through the core smrti operations. All examples are synchronous Python -- no `async`/`await` needed.

## Connect

```python
from smrti import Memory

memory = Memory.connect("postgresql://user:pass@localhost:5432/myapp")
```

You can pass configuration overrides as keyword arguments:

```python
memory = Memory.connect(
    "postgresql://user:pass@localhost:5432/myapp",
    search_mode="hybrid",
    search_limit=20,
    default_namespace="my_agent",
)
```

## Add nodes

Every node needs a `node_type` and `content`. Optionally include an `embedding` (a list of floats) and the `model_name` that produced it.

```python
result = memory.add_nodes([
    {
        "node_type": "person",
        "content": "Alice is a software engineer in Berlin.",
        "embedding": [0.1, 0.2, 0.3, ...],  # your pre-computed vector
        "model_name": "text-embedding-3-small",
    },
    {
        "node_type": "person",
        "content": "Bob is a designer in Tokyo.",
        "embedding": [0.4, 0.5, 0.6, ...],
        "model_name": "text-embedding-3-small",
    },
])

print(result["node_ids"])   # ['uuid-1', 'uuid-2']
print(result["_meta"])      # event_ids, namespace, count, duration_ms
```

## Add edges

Edges connect two nodes with a typed, directed relationship.

```python
result = memory.add_edges([{
    "source_node_id": result["node_ids"][0],
    "target_node_id": result["node_ids"][1],
    "edge_type": "works_with",
    "metadata": {"since": "2024"},
}])

print(result["edge_ids"])  # ['uuid-3']
```

## Search

smrti supports three search modes: `vector`, `text`, and `hybrid`. You provide the query vector and/or text query yourself.

### Vector search

```python
results = memory.search(
    query_vector=[0.1, 0.2, 0.3, ...],
    mode="vector",
)
for r in results["results"]:
    print(r["content"], r["similarity"])
```

### Text search

```python
results = memory.search(
    text_query="software engineer",
    mode="text",
)
```

### Hybrid search (default)

Combines vector and text search using Reciprocal Rank Fusion.

```python
results = memory.search(
    query_vector=[0.1, 0.2, 0.3, ...],
    text_query="software engineer",
    mode="hybrid",
)
```

### Search filters

```python
results = memory.search(
    query_vector=[0.1, 0.2, 0.3, ...],
    text_query="engineer",
    mode="hybrid",
    node_type="person",
    metadata_filter={"department": "engineering"},
    after="2024-01-01",
    limit=5,
    min_similarity=0.7,
)
```

## Traverse the graph

Walk outward from a node along edges.

```python
graph = memory.traverse(
    node_id="uuid-1",
    depth=2,
    edge_types="works_with,manages",
    max_nodes=50,
)
for node in graph["nodes"]:
    print(node["node_id"], node["content"])
for edge in graph["edges"]:
    print(edge["source_node_id"], "->", edge["target_node_id"], edge["edge_type"])
```

## Get or create

Atomically fetch an existing node or create it if it does not exist. Matching is done by `node_key` (if provided) or by `content` + `node_type`.

```python
result = memory.get_or_create(
    content="Alice",
    node_type="person",
    node_key="alice-001",
)
print(result["node_id"], result["created"])  # uuid, True/False
```

## Aggregate

Compute summary statistics over edges of a given type.

```python
stats = memory.aggregate("works_with", metadata_key="since")
print(stats)
# {'count': 5, 'total': ..., 'average': ..., 'minimum': ..., 'maximum': ..., '_meta': {...}}
```

## Session state

Session state is a key-value store scoped to a session ID. Use it for working memory that does not belong in the knowledge graph (e.g., conversation turn count, user preferences for the current session).

```python
memory.state_set("turn_count", 1, session_id="sess-abc")
memory.state_set("user_goal", "book a flight", session_id="sess-abc")

result = memory.state_get("turn_count", session_id="sess-abc")
print(result["value"])  # 1

entries = memory.state_list(session_id="sess-abc")
print(entries["entries"])  # [{'key': 'turn_count', 'value': 1}, ...]

memory.state_delete("user_goal", session_id="sess-abc")
memory.state_clear(session_id="sess-abc")
```

Session state entries can have a TTL (time-to-live) in seconds:

```python
memory.state_set("temp_token", "abc123", session_id="sess-abc", ttl_seconds=300)
```

## Close the connection

```python
memory.close()
```

## Every method returns `_meta`

All smrti methods return a dict that includes a `_meta` key with operational metadata: duration, event IDs, namespaces used, search modes, and more. This is useful for observability and debugging.
