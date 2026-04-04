# Core concepts

## What smrti is

smrti is a **graph-based memory store** for AI agents. It provides:

- A knowledge graph (nodes + edges) backed by PostgreSQL
- Vector, text, and hybrid search over nodes
- An append-only event log for auditability and replication
- Session state (key-value working memory)
- A sync Python API and an async Rust API

smrti is a **dumb storage layer**. It does not call LLMs, run extraction pipelines, or compute embeddings. Your application is responsible for generating embeddings and deciding what to store.

## Nodes

A **node** is the basic unit of knowledge. Every node has:

| Field | Required | Description |
|---|---|---|
| `node_type` | yes | Category string (e.g. `"person"`, `"fact"`, `"document"`) |
| `content` | yes | The text content of the node |
| `node_key` | no | A stable, human-readable key for deduplication |
| `content_type` | no | MIME-like hint (default `"text"`) |
| `metadata` | no | Arbitrary JSON object |
| `embedding` | no | Pre-computed vector (list of floats) |
| `model_name` | no | Name of the model that produced the embedding |

Nodes are identified by UUIDs returned as strings.

## Edges

An **edge** is a directed, typed relationship between two nodes.

| Field | Required | Description |
|---|---|---|
| `source_node_id` | yes | UUID string of the source node |
| `target_node_id` | yes | UUID string of the target node |
| `edge_type` | yes | Relationship type (e.g. `"works_with"`, `"mentions"`) |
| `metadata` | no | Arbitrary JSON object |
| `valid_from` | no | ISO 8601 timestamp -- when the relationship starts |
| `valid_to` | no | ISO 8601 timestamp -- when the relationship ends |

Edges support temporal validity, so you can model relationships that change over time.

## Events

Every write operation (add, update, retract, merge) produces one or more **events** in an append-only log. Events are the source of truth -- the current graph state is a materialized view of the event log.

Events enable:

- **Auditability**: see exactly what changed and when
- **Replication**: export events from one instance and import into another
- **Time travel**: reconstruct past states by replaying a subset of events

## Namespaces

Namespaces provide **tenant isolation** within a single database. Every node, edge, and session state entry belongs to a namespace.

- Default namespace: `"default"` (configurable via `default_namespace`)
- Most methods accept an optional `namespace` parameter
- Search can span multiple namespaces via the `namespaces` parameter
- `purge_namespace()` physically deletes all data for a namespace (GDPR)

## Search modes

smrti supports three search modes:

| Mode | Requires | How it works |
|---|---|---|
| `vector` | `query_vector` | Cosine similarity (or L2/inner product) against stored embeddings via pgvector HNSW index |
| `text` | `text_query` | PostgreSQL full-text search (`tsvector`/`tsquery`) with optional trigram fallback |
| `hybrid` | both | Runs vector and text search independently, then fuses results with Reciprocal Rank Fusion (RRF) |

The default mode is `hybrid` (configurable via `search_mode`).

**You provide the query vector.** smrti does not call an embedding API. Your code must embed the query text using the same model you used to embed your nodes, then pass the resulting vector to `search()`.

## Session state

Session state is a **key-value store** scoped by namespace and session ID. It is designed for ephemeral working memory that does not belong in the knowledge graph:

- Conversation context (turn count, current topic)
- Temporary user preferences
- Tool execution state

Session state entries can have an optional TTL (time-to-live) in seconds. Expired entries are pruned automatically.

## Dual API

smrti provides two APIs:

1. **Python (sync)**: `from smrti import Memory` -- all methods are blocking. Internally uses `block_on` over a Tokio runtime. No `asyncio` needed.
2. **Rust (async)**: `smrti_core::Memory` -- native async API using `sqlx` and `tokio`.

The Python API is a thin PyO3 wrapper over the Rust core. There is no business logic in the Python layer.

## The `_meta` envelope

Every method returns a dict (Python) or JSON object (Rust) that includes a `_meta` key:

```python
result = memory.add_nodes([{"node_type": "fact", "content": "The sky is blue"}])
print(result["_meta"])
# {
#     "event_ids": [42],
#     "namespace": "default",
#     "count": 1,
#     "duration_ms": 3.2,
# }
```

`_meta` always includes `duration_ms`. Depending on the operation it may also include `event_ids`, `namespace`, `search_mode`, `search_modes_used`, `returned`, and other fields. This metadata is designed for observability -- you can log it, send it to your telemetry backend, or surface it to end users.

## The A1 principle

smrti's API is designed so that an LLM can call it directly as a tool. This means:

- All IDs are strings (not UUIDs or integers)
- All parameters are flat (no nested config objects)
- All responses include `_meta` so the LLM can reason about what happened
- Errors are descriptive strings, not codes

If you are building an agent, you can expose smrti methods as tool definitions and the LLM will be able to use them without additional translation.
