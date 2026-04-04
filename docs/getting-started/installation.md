# Installation

## Requirements

- **Python 3.9+**
- **PostgreSQL 15+** with the [pgvector](https://github.com/pgvector/pgvector) extension installed

## Install smrti

```bash
pip install smrti
```

smrti is a native Rust extension built with [maturin](https://www.maturin.rs/). The `pip install` command installs a pre-built wheel (no Rust toolchain needed on your machine).

## Database setup

Create a PostgreSQL database and enable pgvector:

```sql
CREATE DATABASE myapp;
\c myapp
CREATE EXTENSION IF NOT EXISTS vector;
```

smrti runs its own migrations on first connect -- no manual schema setup required.

## Verify the installation

```python
from smrti import Memory

memory = Memory.connect("postgresql://user:pass@localhost:5432/myapp")
result = memory.add_nodes([{
    "node_type": "test",
    "content": "Hello from smrti",
}])
print(result)
# {'node_ids': ['...'], '_meta': {'event_ids': [...], 'namespace': 'default', 'count': 1, ...}}
memory.close()
```

If the snippet above runs without errors, smrti is installed and connected.

## Notes

- **No embedding provider required.** smrti is a storage layer. You compute embeddings externally (using OpenAI, Ollama, sentence-transformers, or any other tool) and pass them in as lists of floats.
- **No LLM provider required.** smrti does not run extraction pipelines or call language models.
- **Sync API.** All Python calls are synchronous. There is no `async`/`await` -- smrti handles concurrency internally via a Tokio runtime.
