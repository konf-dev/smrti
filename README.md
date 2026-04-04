# smrti

Graph-based memory for AI agents, built on PostgreSQL + pgvector.

smrti gives AI agents persistent, searchable, structured memory using a knowledge graph. Event-sourced, multi-tenant, fully configurable. Written in Rust, with Python bindings planned.

## Features

- **Knowledge graph** — nodes + typed edges + vector embeddings
- **Hybrid search** — vector similarity + full-text + trigram, fused with RRF
- **Event-sourced** — append-only log, projections rebuildable from events
- **Multi-tenant** — namespace isolation with multi-namespace search
- **Session state** — lightweight KV store for agent working memory with TTL
- **Temporal edges** — validity intervals for time-bounded relationships
- **Dual API** — LLM-friendly flat API + typed Rust API
- **Fully configurable** — every default, threshold, and algorithm is a parameter
- **Production-grade** — parameterized SQL, batch transactions, advisory locking, GDPR compliance
- **OpenTelemetry** — optional instrumentation, compatible with Langfuse, Jaeger, etc.

## Install (Rust)

```toml
[dependencies]
smrti-core = "0.1"
```

Requires PostgreSQL 15+ with [pgvector](https://github.com/pgvector/pgvector).

## Quick Start

```rust
use smrti_core::{Memory, SmrtiConfig};
use serde_json::json;

#[tokio::main]
async fn main() -> smrti_core::Result<()> {
    let config: SmrtiConfig = serde_json::from_value(json!({
        "dsn": "postgresql://localhost/mydb"
    }))?;

    let mut memory = Memory::connect(config).await?;

    // Store nodes with pre-computed embeddings
    let result = memory.add_nodes(&[
        json!({
            "node_type": "person",
            "content": "Alice is a software engineer at Acme",
            "embedding": [0.1, 0.2, 0.3],
            "model_name": "nomic-embed-text"
        }),
    ], None).await?;

    // Search (vector + text hybrid)
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

## Documentation

- [Core Concepts](docs/getting-started/concepts.md)
- [Search Guide](docs/guides/search.md)
- [Configuration](docs/guides/configuration.md)
- [Error Handling](docs/guides/error-handling.md)
- [Technical Spec](docs/improvements/spec.md)

## Architecture

smrti is a **dumb storage layer** — no built-in LLM calls or embedding generation. Callers provide pre-computed data. Two API layers:

- **Memory** (Layer 1): flat params, string IDs, JSON returns with `_meta` — designed for LLM tool calling
- **StorageProvider** (Layer 2): typed params, UUID, Rust structs — for custom pipelines

## Status

- **smrti-core** (Rust): Complete, 40 tests passing
- **Python bindings** (PyO3): Planned
- **Konflux integration**: Planned

## License

[MIT](LICENSE)
