# smrti

**Graph-based memory for AI agents, built on PostgreSQL + pgvector.**

smrti gives AI agents persistent, searchable, structured memory using a knowledge graph. Event-sourced, multi-tenant, LLM-integrated but model-agnostic.

## Why smrti?

Most agent memory solutions are either too simple (flat vector stores) or too heavy (full graph databases). smrti sits in the middle: a Python library that stores memories as a knowledge graph in your existing PostgreSQL database.

- **Not just vectors** — typed relationships between memories enable structured queries
- **Not just a database** — extraction pipeline, hybrid search, and an API designed for LLM tool calling
- **Not a service** — `pip install` and go, runs in your process

## Key Features

- **Knowledge graph** — nodes + typed edges + vector embeddings
- **Hybrid search** — vector similarity + full-text + trigram, fused with RRF
- **Event-sourced** — append-only log, projections rebuildable from events
- **Multi-tenant** — namespace isolation with multi-namespace search
- **LLM-integrated** — extraction pipeline with configurable models and prompts
- **Temporal edges** — validity intervals for time-bounded relationships
- **Dual API** — simple flat API for LLMs, typed API for developers
- **Fully configurable** — every default, threshold, and algorithm is a parameter
- **OpenTelemetry** — optional instrumentation for any observability backend

## Quick Start

```python
from smrti import Memory, SmrtiConfig
from smrti.embedding.ollama import OllamaEmbedding

memory = Memory(SmrtiConfig(
    dsn="postgresql://localhost/mydb",
    embedding_provider=OllamaEmbedding(),
))
await memory.connect()

# Store memories
ids = await memory.add_nodes([
    {"node_type": "person", "content": "Alice is a software engineer"},
])

# Search
results = await memory.search("engineer")

await memory.close()
```

## Next Steps

- [Installation](getting-started/installation.md) — set up PostgreSQL, pgvector, and smrti
- [Quick Start Tutorial](getting-started/quickstart.md) — full working example
- [Core Concepts](getting-started/concepts.md) — understand the graph memory model
- [Search Guide](guides/search.md) — vector, text, and hybrid search
- [Configuration](guides/configuration.md) — every parameter explained
