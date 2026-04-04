# smrti

**Graph-based memory for AI agents, built on PostgreSQL + pgvector.**

smrti gives AI agents persistent, searchable, structured memory using a knowledge graph. Event-sourced, multi-tenant, fully configurable. Written in Rust, with Python bindings via PyO3.

## Why smrti?

Most agent memory solutions are either too simple (flat vector stores) or too heavy (full graph databases). smrti sits in the middle: a library that stores memories as a knowledge graph in your existing PostgreSQL database.

- **Not just vectors** — typed relationships between memories enable structured queries
- **Not just a database** — hybrid search, graph traversal, and an API designed for LLM tool calling
- **Not a service** — install and go, runs in your process
- **Not opinionated** — no built-in LLM or embedding calls, you bring your own

## Key Features

- **Knowledge graph** — nodes + typed edges + vector embeddings
- **Hybrid search** — vector similarity + full-text + trigram, fused with RRF
- **Event-sourced** — append-only log, projections rebuildable from events
- **Multi-tenant** — namespace isolation with multi-namespace search
- **Session state** — lightweight KV store for agent working memory with TTL
- **Temporal edges** — validity intervals for time-bounded relationships
- **Dual API** — simple flat API for LLMs, typed API for developers
- **Fully configurable** — every default, threshold, and algorithm is a parameter
- **Production-grade** — parameterized SQL, batch transactions, GDPR compliance
- **OpenTelemetry** — optional instrumentation for any observability backend

## Quick Start (Python)

```python
from smrti import Memory

memory = Memory.connect("postgresql://localhost/mydb")

# Store nodes with pre-computed embeddings
result = memory.add_nodes([{
    "node_type": "person",
    "content": "Alice is a software engineer",
    "embedding": [0.1, 0.2, 0.3],
    "model_name": "nomic-embed-text",
}])

# Hybrid search (vector + text)
results = memory.search(
    query_vector=[0.1, 0.2, 0.3],
    text_query="engineer",
    mode="hybrid",
)

memory.close()
```

## Next Steps

- [Installation](getting-started/installation.md) — set up PostgreSQL, pgvector, and smrti
- [Quick Start Tutorial](getting-started/quickstart.md) — full working example
- [Core Concepts](getting-started/concepts.md) — understand the graph memory model
- [Search Guide](guides/search.md) — vector, text, and hybrid search
- [Configuration](guides/configuration.md) — every parameter explained
