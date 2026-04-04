# smrti Implementation Plan — Rust

## Context

smrti is an open-source library providing graph-based memory for AI agents, built on PostgreSQL + pgvector. The spec (`docs/improvements/spec.md`) and user docs are written and define the API contract. Infrastructure (CI, docs tooling, GitHub templates) is set up.

**Decision: Rust core with Python bindings (D30-D32).**

The existing Python prototype will be deleted. The spec defines behavior; the implementation is now Rust.

### Design Decisions D30-D32

- **D30 — Rust core with Python bindings (PyO3):** smrti-core is written in Rust. Python users get `pip install smrti` via PyO3 bindings. Rust users get `cargo add smrti-core`. The Rust crate is the single source of truth for all behavior. Rust gives compile-time trait enforcement, native Konflux integration, single-binary deployment, and memory safety.
- **D31 — Postgres first, SQLite later (stubbed):** PostgresProvider (sqlx + pgvector) is the first implementation. SqliteProvider is stubbed in the trait but implemented after the Postgres path is mature. Both must pass the identical behavioral test suite.
- **D32 — Three distribution targets:** `smrti-core` (crates.io), `smrti` (PyPI via PyO3), `konf-smrti` (Konflux tool integration). Each serves a different consumer without coupling them.

---

## Crate Dependencies

All dependencies for smrti-core and related crates.

| Crate | Version | Purpose |
|-------|---------|---------|
| `serde` | 1 | Serialization/deserialization derive macros for all structs |
| `serde_json` | 1 | JSON Value type used as Memory return type; PyO3 maps to Python dicts |
| `schemars` | 0.8 | JSON Schema generation from Rust types (ExtractionResult -> LLM structured output) |
| `validator` | 0.18 | Declarative validation for SmrtiConfig fields |
| `typed-builder` | 0.20 | Builder pattern for SmrtiConfig |
| `sqlx` | 0.8 | Async PostgreSQL driver with compile-time SQL checking |
| `pgvector` | 0.4 | pgvector type support for sqlx (vector columns, HNSW ops) |
| `thiserror` | 2 | Derive macro for SmrtiError enum |
| `reqwest` | 0.12 | HTTP client for embedding providers (Ollama, OpenAI) and LLM providers |
| `figment` | 0.10 | Config loading from environment variables, TOML files, and defaults |
| `tracing` | 0.1 | Structured diagnostics (zero-cost when no subscriber configured) |
| `tracing-opentelemetry` | 0.28 | OTEL export for tracing spans (feature-gated under `telemetry`) |
| `pyo3` | 0.22 | Python bindings (smrti-python crate only) |
| `testcontainers` | 0.23 | Integration tests with Dockerized PostgreSQL + pgvector |
| `uuid` | 1 | UUID v4 generation for node/edge/embedding IDs |
| `chrono` | 0.4 | DateTime types for timestamps and temporal validity |
| `tokio` | 1 | Async runtime |
| `async-trait` | 0.1 | Async methods in traits (StorageProvider, EmbeddingProvider, LlmProvider) |

Feature flags:

| Feature | Crates Enabled | Default |
|---------|---------------|---------|
| `telemetry` | `tracing-opentelemetry`, `opentelemetry`, `opentelemetry-otlp` | off |
| `python` | `pyo3` | off (enabled only in smrti-python) |

---

## Crate Structure

```
smrti/                          # This repo (monorepo)
├── smrti-core/                 # Rust crate — the library
│   ├── Cargo.toml
│   └── src/
│       ├── lib.rs              # Public API re-exports
│       ├── config.rs           # SmrtiConfig (serde + validator + typed-builder)
│       ├── models.rs           # Node, Edge, Event, SearchResult, etc.
│       ├── events.rs           # EventType enum, Event struct
│       ├── error.rs            # Error types (thiserror)
│       ├── provider/
│       │   ├── mod.rs          # StorageProvider trait
│       │   ├── postgres.rs     # PostgresProvider (sqlx + pgvector)
│       │   └── sqlite.rs       # SqliteProvider (stub, future)
│       ├── search.rs           # SearchMode, EdgeFilter, hybrid RRF logic
│       ├── memory.rs           # Memory struct (high-level API, wraps provider)
│       ├── telemetry.rs        # OTEL (tracing crate integration)
│       └── sql/
│           └── migrations/
│               └── v001_initial.sql
├── smrti-python/               # PyO3 bindings
│   ├── Cargo.toml
│   ├── pyproject.toml
│   └── src/
│       └── lib.rs
├── konf-smrti/                 # Konflux tool integration
│   ├── Cargo.toml
│   └── src/
│       └── lib.rs
├── tests/
│   └── fixtures/               # Shared JSON test fixtures (all three surfaces)
│       ├── add_nodes.json
│       ├── search_hybrid.json
│       ├── traverse.json
│       └── ...
├── docs/                       # Already written
├── .github/                    # Already set up
├── mkdocs.yml
├── llms.txt
├── README.md
└── CHANGELOG.md
```

---

## Consistency Enforcement Architecture

smrti ships three distribution targets (D32). All three must behave identically.

### Rust Trait IS the Spec

The `StorageProvider` trait is the single source of truth for provider behavior. The Rust compiler enforces that every provider implements every method with the correct signature. Adding a method to `StorageProvider` forces implementation in all providers — no runtime duck-typing.

### Shared JSON Test Fixtures

Behavioral tests are defined as JSON fixtures in `tests/fixtures/`. Each fixture defines input parameters, expected output structure, `_meta` fields, and error conditions. The same fixtures are loaded by:

1. **Rust integration tests** (`smrti-core/tests/`) — native deserialization
2. **Python integration tests** (`tests/`) — loaded via `json.load()`, called through PyO3 bindings
3. **Konflux integration tests** (`konf-smrti/tests/`) — loaded and executed as workflow tool calls

All three test suites must pass in CI. A fixture failure in any surface blocks the release.

### Thin Python Bindings

The `smrti-python` crate contains zero business logic. It is purely a translation layer:

- Rust `Result<Value>` -> Python `dict` (or raises `SmrtiError`)
- Rust `async fn` -> Python `async def` (via `pyo3-asyncio`)
- Rust `SmrtiConfig` -> Python `__init__` kwargs
- Rust `SmrtiError` variants -> Python `SmrtiError` exception with `.code` attribute

No validation, no SQL, no embedding logic, no extraction logic in the Python layer.

### Config Validated Once

`SmrtiConfig` validation happens in Rust via the `validator` crate. All three surfaces pass config through the same Rust validation path. No surface-specific validation exists.

### CI Pipeline

```
cargo test                    # Rust unit + integration (testcontainers)
cargo test -p smrti-python    # PyO3 binding tests
cargo test -p konf-smrti      # Konflux integration tests
maturin develop && pytest     # Python-side behavioral tests (shared fixtures)
cargo clippy -- -D warnings   # Lint
```

---

## Documentation Structure

User-facing docs use tabbed examples showing all three surfaces where applicable:

```
docs/
├── index.md                # Overview
├── quickstart.md           # Getting started (tabbed: Python / Rust / Konflux)
├── concepts/
│   ├── architecture.md     # Dual-layer diagram
│   ├── events.md           # Event sourcing model
│   ├── search.md           # Hybrid search explained
│   └── namespaces.md       # Multi-tenant isolation
├── guides/
│   ├── extraction.md       # LLM extraction pipeline
│   ├── custom-provider.md  # Implementing StorageProvider
│   └── embedding.md        # Embedding provider setup
├── api/                    # Auto-generated from rustdoc + PyO3 stubs
├── improvements/
│   ├── spec.md             # Technical specification
│   └── plan.md             # This document
└── decisions.md            # Design decisions D1-D32
```

Tabbed examples (using mkdocs-material tabs):

````markdown
=== "Python"
    ```python
    from smrti import Memory

    memory = await Memory.connect(dsn="postgresql://localhost/mydb")
    result = await memory.search("quarterly revenue")
    ```

=== "Rust"
    ```rust
    use smrti_core::Memory;

    let memory = Memory::connect(config).await?;
    let result = memory.search(SearchOpts::text("quarterly revenue")).await?;
    ```

=== "Konflux"
    ```yaml
    tools:
      - smrti.search:
          query: "quarterly revenue"
    ```
````

---

## Implementation Phases

### Phase 1: Models, Events, Errors, Config

Pure Rust types. No async, no database. Fully testable.

**`models.rs`**: Serde structs matching the spec:
- `Node`, `Edge` (with `is_retracted`, temporal validity)
- `SearchResult` (with `matched_by: Vec<String>`)
- `GraphResult`
- `CandidateNode`, `CandidateEdge`, `ExtractionResult` (derive `schemars::JsonSchema`)
- `EdgeFilter` (for edge-based search)
- All derive `Serialize, Deserialize, Debug, Clone`

**`events.rs`**:
- `EventType` enum (serde string representation)
- `Event` struct with `id: Option<i64>`, `namespace`, `event_type`, `payload: Value`, `metadata: Option<Value>`, `created_at: Option<DateTime<Utc>>`
- Includes `NODES_MERGED` event type

**`error.rs`**: thiserror-based hierarchy:
```rust
#[derive(Debug, thiserror::Error)]
pub enum SmrtiError {
    #[error("Connection failed: {0}")]
    Connection(String),
    #[error("Migration failed: {0}")]
    Migration(String),
    #[error("Event error: {0}")]
    Event(String),
    #[error("Node '{node_id}' not found in namespace '{namespace}'")]
    NodeNotFound { node_id: String, namespace: String },
    #[error("Edge '{edge_id}' not found")]
    EdgeNotFound { edge_id: String },
    #[error("Validation error: {0}")]
    Validation(String),
    #[error("Search error: {0}")]
    Search(String),
    #[error("Embedding error: {0}")]
    Embedding(String),
    #[error("Namespace error: {0}")]
    Namespace(String),
    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),
}
```

**`config.rs`**: SmrtiConfig as a serde struct with `validator` + `typed-builder`:
- All fields from spec section 5
- `impl SmrtiConfig { fn validate(&self) -> Result<(), SmrtiError> }`
- Builder pattern: `SmrtiConfig::builder().dsn("...").build()?`
- `figment` for loading from env vars, TOML files, and defaults

**Tests**: Unit tests for serialization round-trips, config validation, error formatting.

### Phase 2: StorageProvider Trait + PostgresProvider

**`provider/mod.rs`**: The trait:
```rust
#[async_trait]
pub trait StorageProvider: Send + Sync {
    async fn connect(&mut self) -> Result<()>;
    async fn close(&mut self) -> Result<()>;
    async fn migrate(&self) -> Result<()>;

    async fn apply_event(&self, event: &Event) -> Result<i64>;

    async fn get_node(&self, node_id: Uuid) -> Result<Option<Node>>;
    async fn get_node_by_key(&self, namespace: &str, node_key: &str) -> Result<Option<Node>>;
    async fn get_or_create_node(&self, namespace: &str, content: &str, node_type: &str, node_key: Option<&str>) -> Result<(Node, bool)>;

    async fn get_edges(&self, node_ids: &[Uuid], direction: Direction, edge_types: Option<&[String]>) -> Result<Vec<Edge>>;

    async fn search_nodes(&self, query: &SearchQuery) -> Result<Vec<SearchResult>>;
    async fn traverse_graph(&self, start: Uuid, depth: u32, edge_types: Option<&[String]>, max_nodes: u32) -> Result<GraphResult>;
    async fn aggregate_edges(&self, query: &AggregateQuery) -> Result<AggregateResult>;

    async fn get_events(&self, after_id: i64, namespace: Option<&str>, limit: i64) -> Result<Vec<Event>>;

    async fn purge_namespace(&self, namespace: &str) -> Result<PurgeResult>;
}
```

**`provider/postgres.rs`**: Full implementation:
- `PostgresProvider { pool: PgPool, config: SmrtiConfig }`
- `connect()`: create pool, run migrations, verify pgvector extension
- `apply_event()`: single transaction — INSERT event + project
- `search_nodes()`: three modes (vector/text/hybrid) with RRF CTE
- `traverse_graph()`: recursive CTE
- `aggregate_edges()`: SQL aggregation with temporal filtering
- `get_or_create_node()`: ON CONFLICT atomicity
- `purge_namespace()`: cascading delete + audit log
- All SQL parameterized via sqlx (compile-time checked where possible)
- HNSW index: created dynamically per model_name + dimension, sanitized identifiers
- Config values used everywhere (no hardcoded defaults)
- `tracing::instrument` on every public method

**`provider/sqlite.rs`**: Stub:
```rust
pub struct SqliteProvider;
// TODO: Implement using rusqlite + sqlite-vec
// Must pass the same test suite as PostgresProvider
```

**`sql/migrations/v001_initial.sql`**: From spec section 3 — all tables, indexes, triggers, views.

**`search.rs`**: Types used by search:
- `SearchMode` enum (Vector, Text, Hybrid)
- `SearchQuery` struct (all search parameters)
- `EdgeFilter` struct
- `AggregateQuery`, `AggregateResult` structs

**Tests**: Integration tests with testcontainers (pgvector Docker image). Coverage:
- Hybrid search (all three modes)
- Edge-filter search
- get_or_create (new + existing + concurrent)
- purge_namespace
- Parameter validation
- Text search with trigram fallback

### Phase 3: Memory (High-Level API)

No embedding providers or extraction pipeline — smrti is a dumb storage layer.
Callers provide pre-computed embeddings and structured data.

**`memory.rs`**: The user-facing API wrapping the provider:
```rust
pub struct Memory {
    config: SmrtiConfig,
    provider: Box<dyn StorageProvider>,
}

impl Memory {
    pub async fn connect(config: SmrtiConfig) -> Result<Self>;
    pub async fn close(&mut self) -> Result<()>;

    // Write (caller provides pre-computed embeddings)
    pub async fn add_nodes(&self, nodes: &[NodeInput], namespace: Option<&str>) -> Result<Value>;
    // NodeInput has optional embedding: Option<Vec<f32>> and model_name: Option<String>
    pub async fn add_edges(&self, edges: &[EdgeInput], namespace: Option<&str>) -> Result<Value>;
    pub async fn get_or_create(&self, content: &str, node_type: &str, ...) -> Result<Value>;
    pub async fn update_node(&self, node_id: &str, ...) -> Result<Value>;
    pub async fn retract_node(&self, node_id: &str, ...) -> Result<Value>;
    pub async fn retract_edge(&self, edge_id: &str, ...) -> Result<Value>;
    pub async fn merge_nodes(&self, keep_id: &str, remove_id: &str, ...) -> Result<Value>;

    // Query (caller provides pre-computed query vector for vector/hybrid modes)
    pub async fn search(&self, opts: SearchOpts) -> Result<Value>;
    // SearchOpts has optional query_vector: Option<Vec<f32>> and text_query: Option<String>
    pub async fn traverse(&self, node_id: &str, ...) -> Result<Value>;
    pub async fn aggregate(&self, edge_type: &str, ...) -> Result<Value>;

    // Scoping
    pub fn scoped(&self, namespace: &str) -> ScopedMemory;

    // Import/Export
    pub async fn export_events(&self, ...) -> Result<Value>;
    pub async fn import_events(&self, events: &[Value]) -> Result<Value>;
    pub async fn rebuild(&self, ...) -> Result<Value>;

    // GDPR
    pub async fn purge_namespace(&self, namespace: &str) -> Result<Value>;
}
```

All `Value` return types include `_meta`. This is the layer that translates between typed Rust (provider) and dict-like JSON (LLM-friendly). The PyO3 bindings expose these Value types as Python dicts.

**Tests**: Unit tests with mock provider.

### Phase 4: Telemetry

**`telemetry.rs`**: Uses the `tracing` crate. OTEL export via `tracing-opentelemetry` (optional feature flag). Zero-cost when no subscriber is configured.

```toml
[features]
default = []
telemetry = ["tracing-opentelemetry", "opentelemetry", "opentelemetry-otlp"]
```

### Phase 5: Python Bindings (smrti-python/)

PyO3 crate that wraps smrti-core:
- `Memory` class exposed as Python async class
- All methods return Python dicts (from serde_json::Value)
- `pip install smrti` via maturin build
- Async support via pyo3-asyncio
- Thin bindings only — zero business logic in Python layer

### Phase 6: Konflux Integration (konf-smrti/)

Rust crate that wraps smrti-core as Konflux workflow tools:
- Registers smrti operations as tool definitions
- In-process, zero-overhead integration
- Uses same SmrtiConfig validation

### Phase 7: Packaging + Release

- Publish `smrti-core` to crates.io
- Publish `smrti` to PyPI (via maturin)
- Publish `konf-smrti` for Konflux
- Update CHANGELOG, llms.txt
- Tag v0.1.0
- CI deploys docs

---

## Key Rust Advantages Over Python Prototype

| Aspect | Python | Rust |
|--------|--------|------|
| Backend abstraction | Protocol (runtime, no enforcement) | Trait (compile-time enforced) |
| SQL safety | String interpolation risk | sqlx compile-time checking |
| Concurrency | GIL, asyncio | Native threads, tokio |
| Telemetry | Optional OTEL lib | tracing crate (zero-cost built-in) |
| Binary deployment | pip + venv + deps | Single binary |
| Konflux integration | HTTP/FFI | In-process, zero overhead |
| Type safety | Runtime (Pydantic) | Compile-time (serde + types) |
| Schema generation | Pydantic model_json_schema() | schemars derive macro |

---

## What Stays the Same

- Spec (`docs/improvements/spec.md`) — defines behavior, language-agnostic parts unchanged
- User docs (quickstart, concepts, guides) — define the Python API (PyO3 surface)
- Design decisions (D1-D32) — all still valid
- SQL schema — identical
- Error messages — identical
- _meta return format — identical
- Test coverage expectations — identical

---

## Verification

After each phase:
```bash
cargo test
cargo clippy -- -D warnings
```

Integration tests require Docker (testcontainers with pgvector).
