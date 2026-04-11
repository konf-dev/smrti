# smrti

Graph-based memory for AI agents, built on PostgreSQL + pgvector.

smrti gives AI agents persistent, searchable, structured memory using a knowledge graph. Event-sourced, multi-tenant. **Dumb storage layer** — no built-in LLM calls or embedding generation. Callers provide pre-computed data. Written in Rust, with Python bindings via PyO3.

## Features

- **Knowledge graph** — nodes + typed edges + vector embeddings
- **Hybrid search** — vector similarity + full-text + trigram, fused with Reciprocal Rank Fusion
- **Event-sourced** — append-only log, projections rebuildable from events
- **Multi-tenant** — namespace isolation with multi-namespace search
- **Session state** — lightweight KV store for agent working memory with TTL
- **Temporal edges** — validity intervals for time-bounded relationships
- **Dual API** — flat `Memory` API (LLM-friendly) + typed `StorageProvider` API (Rust)
- **Configurable** — every default, threshold, and algorithm is a parameter

## Install (Rust)

```toml
[dependencies]
smrti-core = "0.1"
```

Requires PostgreSQL 15+ with [pgvector](https://github.com/pgvector/pgvector).

## Quick start (Rust)

```rust
use smrti_core::{Memory, SmrtiConfig};
use serde_json::json;

#[tokio::main]
async fn main() -> smrti_core::Result<()> {
    let config: SmrtiConfig = serde_json::from_value(json!({
        "dsn": "postgresql://localhost/mydb"
    }))?;

    let mut memory = Memory::connect(config).await?;

    // Store a node with a pre-computed embedding
    memory.add_nodes(&[
        json!({
            "node_type": "person",
            "content": "Alice is a software engineer at Acme",
            "embedding": [0.1, 0.2, 0.3],
            "model_name": "nomic-embed-text"
        }),
    ], None).await?;

    // Hybrid search (vector + text)
    let results = memory.search(
        Some(vec![0.1, 0.2, 0.3]),  // query vector
        Some("engineer"),             // text query
        None,                         // namespaces (default)
        Some("hybrid"),               // mode
        None, None, None, None, None, None, None, None,
    ).await?;

    memory.close().await?;
    Ok(())
}
```

## Architecture

smrti has two API layers:

- **`Memory`** (Layer 1): flat params, string IDs, JSON returns with `_meta` — designed for LLM tool calling
- **`StorageProvider`** (Layer 2): typed params, UUIDs, Rust structs — for custom pipelines

Both layers share the same underlying storage. Choose Layer 1 for most agent work; drop to Layer 2 only when you need the typed API for custom data flows.

## Documentation

- [`docs/index.md`](docs/index.md) — entry point
- [`docs/getting-started/`](docs/getting-started/) — concepts, installation, quickstart
- [`docs/guides/search.md`](docs/guides/search.md) — search modes (vector / text / hybrid)
- [`docs/guides/configuration.md`](docs/guides/configuration.md) — all configurable parameters
- [`docs/guides/error-handling.md`](docs/guides/error-handling.md) — error types and recovery
- [`docs/decisions.md`](docs/decisions.md) — architectural decision records

## Konf integration

The [`konf-tool-memory-smrti/`](konf-tool-memory-smrti/) crate is the bridge that implements konf's `MemoryBackend` trait over smrti. It's the canonical backend for konf memory. See [github.com/konf-dev/konf](https://github.com/konf-dev/konf).

## Status

- **`smrti-core`** (Rust): complete, 40 tests passing
- **Python bindings** (PyO3, `smrti-python/`): in development
- **`konf-tool-memory-smrti`**: shipping — used by konf MCP servers

## License

[MIT](LICENSE)
