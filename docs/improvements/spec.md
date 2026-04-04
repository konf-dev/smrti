# smrti Technical Specification

Version: 0.3.0-draft
Date: 2026-04-04

> **Implementation language: Rust.** Python bindings via PyO3.

### Distribution Targets

| Artifact | Registry | Description |
|----------|----------|-------------|
| `smrti-core` | crates.io | Rust crate — the library. All logic lives here. |
| `smrti` | PyPI | Python package built with PyO3/maturin. Wraps smrti-core. |
| `konf-smrti` | Konflux | Integration crate for the Konflux agent runtime. |

---

## 1. Overview

smrti is a Rust library (with Python bindings via PyO3) that provides graph-based storage and retrieval for AI agent memory, built on PostgreSQL and pgvector. It is a **dumb storage layer with no built-in intelligence** — it does not call LLMs, generate embeddings, or run extraction pipelines. It accepts pre-computed data (nodes, edges, embeddings) and provides powerful search (vector, text, hybrid), graph traversal, and aggregation.

The LLM integration (extraction, embedding, reconciliation) is the **caller's responsibility**. Users connect their own LLM and embedding providers — via Konflux workflows, custom code, or any orchestration layer. smrti provides the storage primitives and API design (flat params, _meta returns, LLM-friendly errors) that make this integration efficient and industry-standard.

smrti is a library (Rust: `smrti-core` crate; Python: `pip install smrti`), not a service; it runs in-process and delegates all storage to PostgreSQL.

---

## 2. Architecture: Dual-Layer API

smrti exposes two layers. Application code (and LLM tool calls) use Layer 1. Only developers extending smrti or building custom pipelines touch Layer 2.

```
+------------------------------------------------------------------+
|  LLM / Agent / Application Code                                  |
+------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------+
|  Layer 1: Memory                                                 |
|  - Flat parameters (str IDs, str dates, simple dicts)            |
|  - Returns plain dicts with _meta key                            |
|  - Validates inputs, translates types, adds _meta                |
|  - Zero SQL, zero database imports                               |
|  - Accepts pre-computed query vectors from caller                |
+------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------+
|  Layer 2: StorageProvider (trait) / PostgresProvider              |
|  - Typed parameters (Uuid, DateTime<Utc>, Rust structs)          |
|  - Returns typed Rust structs (Node, Edge, SearchResult)         |
|  - Owns all SQL, connection pooling, migrations                  |
|  - apply_event() is the single write path                        |
|  - All reads are projections from the event log                  |
+------------------------------------------------------------------+
        |
        v
+------------------------------------------------------------------+
|  PostgreSQL + pgvector + pg_trgm                                 |
|  - events (append-only log)                                      |
|  - nodes, edges (projections)                                    |
|  - node_embeddings (vector storage)                              |
+------------------------------------------------------------------+
```

**Rules:**
- Memory MUST NOT import sqlx, contain SQL strings, or reference database-specific types.
- Memory MUST call Provider methods for all data operations.
- Provider MUST return typed Rust structs; Memory converts them to `serde_json::Value` (which PyO3 maps to Python dicts).
- Every Value returned by Memory MUST contain a `_meta` key.

**Distribution targets (D32):** This architecture applies to all three surfaces — Rust (`smrti-core`), Python (`smrti` via PyO3), and Konflux (`konf-smrti`). Memory and StorageProvider are Rust structs/traits. Memory returns `serde_json::Value` which maps to Python dicts via PyO3. See section 16 for consistency enforcement across surfaces.

---

## 3. Data Model

### 3.1 Extensions

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for trigram text search fallback
```

### 3.2 smrti_meta

Migration tracking and runtime metadata.

```sql
CREATE TABLE IF NOT EXISTS smrti_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

Used for: migration state (`migration:v001_initial.sql`), HNSW index tracking (`hnsw_index:{model}:{dim}`), schema version.

### 3.3 events

The append-only event log. Source of truth for all data.

```sql
CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    namespace  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    JSONB NOT NULL DEFAULT '{}',
    metadata   JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_namespace
    ON events (namespace);
CREATE INDEX IF NOT EXISTS idx_events_namespace_created
    ON events (namespace, created_at DESC);
```

- `id`: Monotonically increasing. Provides total ordering ("Arrow of Time").
- `event_type`: One of the EventType enum values (see section 4).
- `payload`: Event-specific data (node fields, edge fields, embedding vectors).
- `metadata`: System metadata (LLM model version, prompt ID, trace IDs). Optional.

### 3.4 nodes

Projection of current node state, derived from NODE_CREATED/NODE_UPDATED/NODE_RETRACTED events.

```sql
CREATE TABLE IF NOT EXISTS nodes (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace     TEXT NOT NULL,
    node_key      TEXT,
    node_type     TEXT NOT NULL,
    content       TEXT NOT NULL,
    content_type  TEXT NOT NULL DEFAULT 'text',
    metadata      JSONB NOT NULL DEFAULT '{}',
    search_vector TSVECTOR,
    is_retracted  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Identity anchoring: node_key unique per namespace (partial index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_namespace_key
    ON nodes (namespace, node_key) WHERE node_key IS NOT NULL;

-- Namespace scoping
CREATE INDEX IF NOT EXISTS idx_nodes_namespace
    ON nodes (namespace);

-- Type filtering within namespace
CREATE INDEX IF NOT EXISTS idx_nodes_namespace_type
    ON nodes (namespace, node_type);

-- Exclude retracted from queries
CREATE INDEX IF NOT EXISTS idx_nodes_namespace_retracted
    ON nodes (namespace, is_retracted);

-- JSONB metadata containment queries (@>)
CREATE INDEX IF NOT EXISTS idx_nodes_metadata
    ON nodes USING GIN (metadata jsonb_path_ops);

-- Full-text search on content
CREATE INDEX IF NOT EXISTS idx_nodes_search_vector
    ON nodes USING GIN (search_vector);

-- Trigram similarity search (fallback when tsvector misses)
CREATE INDEX IF NOT EXISTS idx_nodes_content_trgm
    ON nodes USING GIN (content gin_trgm_ops);
```

**tsvector trigger:**

The trigger uses the SAME language config as search queries. This is critical — if the trigger uses `'simple'` but queries use `'english'`, stemming won't match ("running" indexed as "running" but queried as "run" = no match).

The migration creates the trigger with the default language (`'english'`). If the user configures a different `search_language`, the provider re-creates the trigger function on connect if the language has changed (checked via smrti_meta).

```sql
CREATE OR REPLACE FUNCTION nodes_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nodes_search_vector
    BEFORE INSERT OR UPDATE OF content ON nodes
    FOR EACH ROW
    EXECUTE FUNCTION nodes_search_vector_update();
```

If the language changes, the provider runs:
```sql
CREATE OR REPLACE FUNCTION nodes_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('NEW_LANGUAGE', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- Then backfill:
UPDATE nodes SET search_vector = to_tsvector('NEW_LANGUAGE', content);
```
And records the current language in `smrti_meta` key `search_language`.

### 3.5 node_embeddings

Separate table for multi-model embedding support.

```sql
CREATE TABLE IF NOT EXISTS node_embeddings (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_id    UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    embedding  vector,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (node_id, model_name)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_node_id
    ON node_embeddings (node_id);
```

- `embedding` column is dimension-agnostic. Declared as `vector` (no dimension) so different models with different dimensions can coexist.
- HNSW indexes are created dynamically per `(model_name, dimension)` pair. See section 3.7.

### 3.6 edges

Typed, directed relationships with temporal validity. Projection from EDGE_ADDED/EDGE_UPDATED/EDGE_RETRACTED events.

```sql
CREATE TABLE IF NOT EXISTS edges (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    namespace      TEXT NOT NULL,
    source_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id UUID NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    edge_type      TEXT NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}',
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to       TIMESTAMPTZ,
    is_retracted   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- No UNIQUE constraint on (source_node_id, target_node_id, edge_type).
-- This is intentional. See Section 11: Append-only edge semantics.

CREATE INDEX IF NOT EXISTS idx_edges_source
    ON edges (source_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_target
    ON edges (target_node_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_namespace_type
    ON edges (namespace, edge_type);
CREATE INDEX IF NOT EXISTS idx_edges_validity
    ON edges (valid_from, valid_to);
```

### 3.7 active_edges VIEW

```sql
CREATE OR REPLACE VIEW active_edges AS
SELECT *
FROM edges
WHERE is_retracted = FALSE
  AND valid_from <= NOW()
  AND (valid_to IS NULL OR valid_to >= NOW());
```

### 3.8 Dynamic HNSW Index Creation

When the first embedding for a given `(model_name, dimension)` pair is stored, PostgresProvider creates a partial HNSW index:

```sql
CREATE INDEX IF NOT EXISTS idx_embeddings_hnsw_{sanitized_model}_{dim}
    ON node_embeddings USING hnsw
    ((embedding::vector({dim})) vector_cosine_ops)
    WHERE model_name = '{model_name}';
```

The index name and existence is tracked in `smrti_meta` with key `hnsw_index:{model_name}:{dim}`. HNSW parameters `m` and `ef_construction` come from `SmrtiConfig.hnsw_m` and `SmrtiConfig.hnsw_ef_construction`.

---

## 4. Event Types

Every mutation in smrti is recorded as an event. The `EventType` enum:

```rust
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum EventType {
    NodeCreated,
    NodeUpdated,
    NodeRetracted,
    EdgeAdded,
    EdgeUpdated,
    EdgeRetracted,
    EmbeddingStored,
    RawInputReceived,
    NodesMerged,
}
```

Serde serializes these as `"NODE_CREATED"`, `"EDGE_ADDED"`, etc. — matching the event_type strings stored in PostgreSQL.

### 4.1 Payload Schemas

**NODE_CREATED**
```json
{
    "id": "uuid-string",
    "namespace": "string",
    "node_key": "string | null",
    "node_type": "string",
    "content": "string",
    "content_type": "string (default: 'text')",
    "metadata": {}
}
```
Projection: INSERT into nodes. ON CONFLICT (namespace, node_key) WHERE node_key IS NOT NULL -> UPDATE content, metadata, updated_at.

**NODE_UPDATED**
```json
{
    "id": "uuid-string",
    "content": "string (optional)",
    "metadata": "{} (optional)",
    "node_type": "string (optional)"
}
```
Projection: UPDATE nodes SET (only provided fields), updated_at = NOW().

**NODE_RETRACTED**
```json
{
    "id": "uuid-string"
}
```
Projection: UPDATE nodes SET is_retracted = TRUE, updated_at = NOW(). No hard delete.

**EDGE_ADDED**
```json
{
    "id": "uuid-string",
    "source_node_id": "uuid-string",
    "target_node_id": "uuid-string",
    "edge_type": "string",
    "metadata": {},
    "valid_from": "ISO 8601 string | null (defaults to NOW())",
    "valid_to": "ISO 8601 string | null (null = currently valid)"
}
```
Projection: INSERT into edges.

**EDGE_UPDATED**
```json
{
    "id": "uuid-string",
    "metadata": "{} (optional)",
    "valid_to": "ISO 8601 string | null (optional)"
}
```
Projection: UPDATE edges SET (only provided fields).

**EDGE_RETRACTED**
```json
{
    "id": "uuid-string"
}
```
Projection: UPDATE edges SET is_retracted = TRUE.

**EMBEDDING_STORED**
```json
{
    "node_id": "uuid-string",
    "model_name": "string",
    "embedding": [float, ...]
}
```
Projection: INSERT into node_embeddings ON CONFLICT (node_id, model_name) DO UPDATE. Then ensure HNSW index exists for this model+dimension.

**RAW_INPUT_RECEIVED**
```json
{
    "text": "string"
}
```
Projection: None. Logged only. Used as audit trail for caller's extraction pipeline.

**NODES_MERGED**
```json
{
    "kept_id": "uuid-string",
    "removed_id": "uuid-string",
    "edges_remapped": 3
}
```
Projection: Retract the removed node. Remap all edges pointing to/from removed_id to point to kept_id. Record the count of remapped edges.

---

## 5. Configuration (SmrtiConfig)

Implemented as a serde `Deserialize` struct with a `validate()` method and builder pattern (using `typed-builder`). Validation uses the `validator` crate for declarative field constraints. Config can be loaded from environment variables, TOML files, or code using `figment`.

```rust
#[derive(Debug, Clone, Deserialize)]
pub struct SmrtiConfig {
    // --- Required ---
    pub dsn: String,
    // PostgreSQL connection string.
    // Example: "postgresql://user:pass@localhost:5432/mydb"
    // Validated: must start with "postgresql://" or "postgres://"

    // --- Namespacing ---
    #[serde(default = "default_namespace")]
    pub default_namespace: String,
    // Namespace used when none is specified in API calls.
    // Default: "default". Validated: non-empty string.

    // --- Connection Pool ---
    #[serde(default = "default_pool_min")]
    pub pool_min: u32,
    // Minimum connections in the sqlx pool.
    // Default: 2. Validated: >= 1

    #[serde(default = "default_pool_max")]
    pub pool_max: u32,
    // Maximum connections in the sqlx pool.
    // Default: 10. Validated: >= pool_min

    // --- Search ---
    #[serde(default = "default_search_limit")]
    pub search_limit: i64,
    // Default number of results for search operations.
    // Default: 10. Validated: >= 1

    #[serde(default)]
    pub min_similarity: f64,
    // Default minimum cosine similarity threshold.
    // Default: 0.0. Validated: 0.0 <= min_similarity <= 1.0

    #[serde(default = "default_search_mode")]
    pub search_mode: String,
    // Default search mode: "vector", "text", or "hybrid".
    // Default: "hybrid". Validated: must be one of these three values.

    #[serde(default = "default_search_language")]
    pub search_language: String,
    // PostgreSQL text search configuration name.
    // Default: "english". Used in to_tsvector() and plainto_tsquery().

    #[serde(default = "default_rrf_k")]
    pub rrf_k: i64,
    // Reciprocal Rank Fusion constant. Higher values smooth rank differences.
    // Default: 60. Validated: >= 1

    #[serde(default = "default_hybrid_candidate_pool")]
    pub hybrid_candidate_pool: i64,
    // Number of candidates to fetch from each search mode before RRF fusion.
    // Default: 100. Validated: >= search_limit

    // --- Traversal ---
    #[serde(default = "default_max_traversal_depth")]
    pub max_traversal_depth: u32,
    // Maximum allowed depth for graph traversal.
    // Default: 5. Validated: >= 1

    #[serde(default = "default_max_traversal_nodes")]
    pub max_traversal_nodes: u32,
    // Maximum nodes returned from a traversal.
    // Default: 100. Validated: >= 1

    // --- Events ---
    #[serde(default = "default_max_events_export")]
    pub max_events_export: i64,
    // Maximum events returned by export_events() in a single call.
    // Default: 10000. Validated: >= 1

    // --- pgvector ---
    #[serde(default = "default_hnsw_m")]
    pub hnsw_m: i32,
    // HNSW index parameter: max number of connections per node.
    // Default: 16. Validated: >= 2

    #[serde(default = "default_hnsw_ef_construction")]
    pub hnsw_ef_construction: i32,
    // HNSW index parameter: size of the dynamic candidate list during construction.
    // Default: 64. Validated: >= 1

    #[serde(default = "default_distance_metric")]
    pub distance_metric: String,
    // Distance metric for vector search: "cosine", "l2", or "inner_product".
    // Default: "cosine". Validated: must be one of these three values.
    // Maps to pgvector ops: vector_cosine_ops, vector_l2_ops, vector_ip_ops.

    // --- Embedding ---
    #[serde(default = "default_embedding_model")]
    pub embedding_model: String,
    // Key stored in node_embeddings.model_name.
    // Default: "default". Typically matches the model name from the embedding provider.
}

impl SmrtiConfig {
    /// Validate all fields. Called by the builder's build() method.
    pub fn validate(&self) -> Result<(), SmrtiError> { /* ... */ }

    /// Builder pattern entry point.
    pub fn builder() -> SmrtiConfigBuilder { /* ... */ }
}
```

The builder pattern allows ergonomic construction:

```rust
let config = SmrtiConfig::builder()
    .dsn("postgresql://localhost/mydb")
    .search_mode("hybrid")
    .build()?;
```

---

## 6. StorageProvider Trait

Complete interface that all storage backends must implement. Uses `async_trait` for async methods in traits.

```rust
use async_trait::async_trait;
use uuid::Uuid;

#[async_trait]
pub trait StorageProvider: Send + Sync {

    /// Initialize connection pool and apply pending migrations.
    ///
    /// Called once at startup. Creates the connection pool, runs
    /// migrations (auto-create tables on first run), and verifies
    /// pgvector extension.
    ///
    /// Errors: SmrtiError::Connection, SmrtiError::Migration
    async fn connect(&mut self) -> Result<()>;

    /// Close the connection pool and release all connections.
    ///
    /// Safe to call multiple times. No-op if already closed.
    async fn close(&mut self) -> Result<()>;

    /// Apply any pending database migrations.
    ///
    /// Reads migration files from sql/migrations/ in sorted order.
    /// Tracks applied migrations in smrti_meta. Idempotent.
    ///
    /// Errors: SmrtiError::Migration
    async fn migrate(&self) -> Result<()>;

    // --- Mutation ---

    /// The single write path. Atomically appends the event to the
    /// event log and updates projections in a single transaction.
    ///
    /// event.id and event.created_at are assigned by the database.
    /// Returns the database-assigned event ID (BIGSERIAL).
    ///
    /// Errors: SmrtiError::Event
    async fn apply_event(&self, event: &Event) -> Result<i64>;

    // --- Node Retrieval ---

    /// Fetch a single node by ID. Returns None if not found.
    /// Includes retracted nodes (caller filters if needed).
    async fn get_node(&self, node_id: Uuid) -> Result<Option<Node>>;

    /// Fetch a node by its identity anchor key within a namespace.
    /// Returns None if not found. Excludes retracted nodes.
    async fn get_node_by_key(&self, namespace: &str, node_key: &str) -> Result<Option<Node>>;

    /// Atomically get an existing node or create a new one.
    ///
    /// If node_key is provided, uses ON CONFLICT (namespace, node_key)
    /// to guarantee no duplicates even under concurrent access.
    ///
    /// If node_key is None, always creates a new node.
    ///
    /// Returns (Node, created) where created is true if a new
    /// node was inserted, false if an existing one was returned.
    ///
    /// SQL (when node_key is provided):
    ///     INSERT INTO nodes (id, namespace, node_key, node_type, content,
    ///                        content_type, metadata)
    ///     VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
    ///     ON CONFLICT (namespace, node_key) WHERE node_key IS NOT NULL
    ///     DO NOTHING
    ///     RETURNING *;
    ///
    ///     If RETURNING yields no rows, the node already existed:
    ///     SELECT * FROM nodes WHERE namespace = $2 AND node_key = $3;
    async fn get_or_create_node(
        &self,
        namespace: &str,
        content: &str,
        node_type: &str,
        node_key: Option<&str>,
        content_type: Option<&str>,
        metadata: Option<&Value>,
    ) -> Result<(Node, bool)>;

    // --- Edge Retrieval ---

    /// Retrieve active edges for one or more nodes.
    ///
    /// direction: "outgoing", "incoming", or "both".
    /// edge_types: Optional filter to specific edge types.
    ///
    /// Returns only active edges (not retracted, temporally valid).
    async fn get_edges(
        &self,
        node_ids: &[Uuid],
        direction: &str,
        edge_types: Option<&[String]>,
    ) -> Result<Vec<Edge>>;

    // --- Search ---

    /// Search nodes using vector similarity, full-text, or hybrid.
    ///
    /// Returns Vec<SearchResult> sorted by relevance.
    ///
    /// Errors: SmrtiError::Search (vector mode without query_vector),
    ///         SmrtiError::Validation (invalid mode)
    async fn search_nodes(&self, query: &SearchQuery) -> Result<Vec<SearchResult>>;

    // --- Traversal ---

    /// BFS graph walk from a starting node.
    ///
    /// Follows active edges (not retracted, temporally valid).
    /// Returns all reachable nodes and edges within depth hops.
    /// Always includes the start node even if it has no edges.
    ///
    /// Errors: SmrtiError::NodeNotFound
    async fn traverse_graph(
        &self,
        start_node_id: Uuid,
        depth: u32,
        edge_types: Option<&[String]>,
        max_nodes: u32,
    ) -> Result<GraphResult>;

    // --- Aggregation ---

    /// SQL-side aggregation on edges of a given type.
    ///
    /// Always returns count. If metadata_key is provided, also returns
    /// total, average, minimum, maximum (any may be None if no numeric values).
    async fn aggregate_edges(&self, query: &AggregateQuery) -> Result<AggregateResult>;

    // --- Event Log ---

    /// Retrieve events from the log, ordered by ID ascending.
    async fn get_events(
        &self,
        after_id: i64,
        namespace: Option<&str>,
        limit: i64,
    ) -> Result<Vec<Event>>;

    // --- GDPR ---

    /// Physically delete ALL data for a namespace.
    /// This is the ONLY operation that violates append-only.
    async fn purge_namespace(&self, namespace: &str) -> Result<PurgeResult>;
}
```

`PostgresProvider` implements this trait using `sqlx` (with compile-time checked queries where possible) and `pgvector`. `SqliteProvider` is stubbed for future implementation using `rusqlite` + `sqlite-vec`. Both providers must pass the identical behavioral test suite — the Rust trait enforces API consistency at compile time (D29, D31).

### 6.1 EdgeFilter Struct

Used by `search_nodes` to filter search results based on their edge relationships.

```rust
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EdgeFilter {
    /// Required: the edge type to filter by.
    pub edge_type: String,

    /// "outgoing", "incoming", or "both". Default: "outgoing".
    #[serde(default = "default_direction")]
    pub direction: String,

    /// If provided, require the edge to connect to this specific node.
    pub target_node_id: Option<Uuid>,

    /// If provided, require the connected node to have this type.
    pub target_node_type: Option<String>,

    /// If provided, require the edge metadata to contain these key-value pairs.
    pub metadata_filter: Option<Value>,
}
```

EdgeFilter generates an EXISTS subquery JOIN:

```sql
-- Example: edge_type="WORKS_AT", target_node_type="company"
AND EXISTS (
    SELECT 1 FROM edges e_filter
    JOIN nodes n_target ON n_target.id = e_filter.target_node_id
    WHERE e_filter.source_node_id = n.id
      AND e_filter.edge_type = 'WORKS_AT'
      AND e_filter.is_retracted = FALSE
      AND e_filter.valid_from <= NOW()
      AND (e_filter.valid_to IS NULL OR e_filter.valid_to >= NOW())
      AND n_target.node_type = 'company'
)
```

---

## 7. Memory Struct API

The Memory struct is the user-facing API. In Rust, all methods return `Result<Value>` where `Value` is `serde_json::Value`. The PyO3 bindings expose these as Python async methods returning dicts. All parameters are flat (strings, integers, floats). String IDs are used instead of UUIDs at this layer.

```rust
pub struct Memory {
    config: SmrtiConfig,
    provider: Box<dyn StorageProvider>,
}

impl Memory {

    // --- Lifecycle ---

    /// Connect to the database and apply migrations.
    /// Must be called before any other method.
    ///
    /// Errors: SmrtiError::Connection, SmrtiError::Migration
    pub async fn connect(config: SmrtiConfig) -> Result<Self>;

    /// Close the database connection pool.
    /// Safe to call multiple times.
    pub async fn close(&mut self) -> Result<()>;

    // --- Write ---

    /// Add one or more nodes to the knowledge graph.
    ///
    /// Each node Value must contain:
    ///     - node_type (str): required
    ///     - content (str): required
    /// Optional:
    ///     - node_key (str): identity anchor key
    ///     - content_type (str): default "text"
    ///     - metadata (object): default {}
    ///     - embedding (Vec<f32>): pre-computed embedding vector
    ///     - model_name (str): embedding model name (default: config.embedding_model)
    ///
    /// If embedding is provided, it is stored in node_embeddings.
    /// If embedding is None, the node is stored without a vector
    /// (searchable by text/metadata but not by vector similarity).
    ///
    /// Returns: {"node_ids": [str, ...],
    ///           "_meta": {"event_ids": [int, ...], "namespace": str, "count": int}}
    ///
    /// Errors: SmrtiError::Validation, SmrtiError::Embedding
    pub async fn add_nodes(&self, nodes: &[Value], namespace: Option<&str>) -> Result<Value>;

    /// Add one or more edges to the knowledge graph.
    ///
    /// Each edge Value must contain:
    ///     - source_node_id (str): UUID of source node
    ///     - target_node_id (str): UUID of target node
    ///     - edge_type (str): relationship type
    /// Optional:
    ///     - metadata (object): default {}
    ///     - valid_from (str): ISO date, default NOW()
    ///     - valid_to (str): ISO date, default None (currently valid)
    ///
    /// Returns: {"edge_ids": [str, ...],
    ///           "_meta": {"event_ids": [int, ...], "namespace": str, "count": int}}
    ///
    /// Errors: SmrtiError::Validation, SmrtiError::NodeNotFound
    pub async fn add_edges(&self, edges: &[Value], namespace: Option<&str>) -> Result<Value>;

    /// Get an existing node or create a new one atomically.
    ///
    /// If node_key is provided, uses database-level uniqueness to prevent
    /// race conditions.
    ///
    /// Returns: {"node_id": str, "created": bool, "node": {node fields...},
    ///           "_meta": {"event_id": int|null, "namespace": str}}
    ///
    /// Note: event_id is null if the node already existed (no event created).
    pub async fn get_or_create(
        &self, content: &str, node_type: &str,
        node_key: Option<&str>, namespace: Option<&str>,
        metadata: Option<&Value>,
    ) -> Result<Value>;

    /// Update fields on an existing node.
    ///
    /// Only provided fields are updated. Re-embeds if content changes.
    ///
    /// Returns: {"node_id": str, "_meta": {"event_id": int, "re_embedded": bool}}
    ///
    /// Errors: SmrtiError::NodeNotFound, SmrtiError::Validation
    pub async fn update_node(
        &self, node_id: &str,
        content: Option<&str>, metadata: Option<&Value>,
        node_type: Option<&str>,
    ) -> Result<Value>;

    /// Soft-delete a node. It remains in the event log but is excluded
    /// from search, traverse, and aggregate operations.
    ///
    /// Returns: {"node_id": str, "_meta": {"event_id": int}}
    ///
    /// Errors: SmrtiError::NodeNotFound
    pub async fn retract_node(&self, node_id: &str) -> Result<Value>;

    /// Soft-delete an edge.
    ///
    /// Returns: {"edge_id": str, "_meta": {"event_id": int}}
    ///
    /// Errors: SmrtiError::EdgeNotFound
    pub async fn retract_edge(&self, edge_id: &str) -> Result<Value>;

    /// Merge two nodes by keeping one and retracting the other.
    ///
    /// All edges pointing to/from remove_id are remapped to keep_id.
    /// The removed node is retracted (soft-deleted).
    ///
    /// Returns: {"kept_id": str, "removed_id": str,
    ///           "_meta": {"event_id": int, "edges_remapped": int}}
    ///
    /// Errors: SmrtiError::NodeNotFound
    pub async fn merge_nodes(&self, keep_id: &str, remove_id: &str) -> Result<Value>;

    // --- Search ---

    /// Find nodes semantically similar to the given content.
    ///
    /// Pure vector search. Embeds the content and searches.
    ///
    /// Returns: {"results": [{"node_id": str, "content": str, "node_type": str,
    ///                         "similarity": float, "metadata": object}, ...],
    ///           "_meta": {"search_mode": "vector", "namespace": [str, ...],
    ///                     "total_candidates": int, "duration_ms": float}}
    pub async fn find_similar(
        &self, content: &str,
        namespace: Option<&str>, node_type: Option<&str>,
        limit: Option<i64>, min_similarity: Option<f64>,
    ) -> Result<Value>;

    /// Search the knowledge graph with hybrid vector + text search.
    ///
    /// Returns: {"results": [{"node_id": str, "content": str, "node_type": str,
    ///                         "similarity": float, "metadata": object,
    ///                         "edges": [edge objects...]}, ...],
    ///           "_meta": {"search_mode": str, "search_modes_used": [str, ...],
    ///                     "namespace": [str, ...], "total_candidates": int,
    ///                     "duration_ms": float, "rrf_k": int|null}}
    pub async fn search(
        &self, query: &str,
        namespace: Option<&str>, mode: Option<&str>,
        node_type: Option<&str>, edge_type: Option<&str>,
        edge_target: Option<&str>, filters: Option<&Value>,
        limit: Option<i64>, min_similarity: Option<f64>,
        after: Option<&str>, before: Option<&str>,
    ) -> Result<Value>;

    // --- Traversal ---

    /// Walk the graph from a starting node.
    ///
    /// Returns: {"nodes": [...], "edges": [...],
    ///           "_meta": {"start_node_id": str, "depth": int,
    ///                     "nodes_found": int, "edges_found": int,
    ///                     "duration_ms": float}}
    ///
    /// Errors: SmrtiError::NodeNotFound
    pub async fn traverse(
        &self, node_id: &str,
        depth: Option<u32>, edge_types: Option<&str>,
        max_nodes: Option<u32>,
    ) -> Result<Value>;

    // --- Aggregation ---

    /// Aggregate over edges of a given type.
    ///
    /// Returns: {"count": int, "total": float|null, "average": float|null,
    ///           "minimum": float|null, "maximum": float|null,
    ///           "_meta": {"edge_type": str, "namespace": [str, ...],
    ///                     "duration_ms": float}}
    pub async fn aggregate(
        &self, edge_type: &str,
        namespace: Option<&str>, metadata_key: Option<&str>,
        filters: Option<&Value>, at_time: Option<&str>,
    ) -> Result<Value>;

    // --- Edge Retrieval ---

    /// Get active edges for a node.
    ///
    /// Returns: {"edges": [...],
    ///           "_meta": {"node_id": str, "direction": str, "count": int}}
    pub async fn get_edges(
        &self, node_id: &str,
        direction: Option<&str>, edge_types: Option<&str>,
    ) -> Result<Value>;

    // --- Import/Export ---

    /// Export events from the log for backup or migration.
    ///
    /// Returns: {"events": [...],
    ///           "_meta": {"count": int, "first_id": int|null, "last_id": int|null}}
    pub async fn export_events(
        &self, after_id: Option<i64>,
        namespace: Option<&str>, limit: Option<i64>,
    ) -> Result<Value>;

    /// Import events by replaying them through apply_event().
    /// Events are applied in order. Each event gets a new database-assigned ID.
    ///
    /// Returns: {"imported": int, "_meta": {"event_id_range": [int, int]}}
    ///
    /// Errors: SmrtiError::Event
    pub async fn import_events(&self, events: &[Value]) -> Result<Value>;

    /// Rebuild projections from the event log.
    ///
    /// Returns: {"events_replayed": int,
    ///           "_meta": {"namespace": str|null, "duration_ms": float}}
    ///
    /// Errors: SmrtiError::Validation (if no namespace and all_namespaces is false)
    pub async fn rebuild(
        &self, namespace: Option<&str>, all_namespaces: bool,
    ) -> Result<Value>;

    // --- GDPR / Compliance ---

    /// Physically delete ALL data for a namespace.
    ///
    /// Returns: {"purged": true, "namespace": str,
    ///           "_meta": {"events_deleted": int, "nodes_deleted": int,
    ///                     "edges_deleted": int}}
    pub async fn purge_namespace(&self, namespace: &str) -> Result<Value>;

    // --- Scoped Context ---

    /// Return a namespace-bound wrapper over this Memory instance.
    /// All calls on the returned object use the given namespace by default.
    /// Explicit namespace params still override.
    /// The underlying provider and connection pool are shared.
    pub fn scoped(&self, namespace: &str) -> ScopedMemory;
}
```

**PyO3 bindings:** The `smrti-python` crate wraps `Memory` as a Python class. All `Result<Value>` return types become Python dicts via PyO3's automatic `serde_json::Value` -> `dict` conversion. Async methods use `pyo3-asyncio` to expose as Python `async def` methods.

---

## 8. Error Contract

All errors are variants of a single `SmrtiError` enum using the `thiserror` derive macro. Each variant includes a human-readable message suitable for LLM consumption. In Python (via PyO3), these map to a `SmrtiError` exception class.

```rust
#[derive(Debug, thiserror::Error)]
pub enum SmrtiError {
    #[error("Connection failed: {0}")]
    Connection(String),
    // When: Database unreachable, pool creation fails, connection timeout.
    // LLM action: Tell user to check database connection/credentials.

    #[error("Migration failed: {0}")]
    Migration(String),
    // When: SQL migration file fails to execute.
    // Message format: "Migration failed: Failed to apply {filename}: {sql_error}"
    // LLM action: Tell user there is a database schema issue, likely version mismatch.

    #[error("Event error: {0}")]
    Event(String),
    // When: apply_event() fails during projection update.
    // Message format: "Event error: Projection failed for {event_type}: {detail}"
    // LLM action: Retry the operation. If persistent, report to developer.

    #[error("Embedding error: {0}")]
    Embedding(String),
    // When: Invalid embedding dimensions, dimension mismatch with existing embeddings for model.
    // LLM action: Check that the embedding vector dimensions match the model's expected dimensions.

    #[error("Node '{node_id}' not found in namespace '{namespace}'")]
    NodeNotFound { node_id: String, namespace: String },
    // When: Operation references a node ID that does not exist.
    // LLM action: Verify the node ID is correct. It may have been retracted.

    #[error("Edge '{edge_id}' not found")]
    EdgeNotFound { edge_id: String },
    // When: Operation references an edge ID that does not exist.
    // LLM action: Verify the edge ID is correct.

    #[error("Validation error: {0}")]
    Validation(String),
    // When: Input validation fails (missing required fields, invalid types,
    // invalid mode strings, empty text, etc.).
    // LLM action: Fix the input parameters and retry.

    #[error("Search error: {0}")]
    Search(String),
    // When: Search operation fails (e.g., vector mode without embedding).
    // LLM action: Check search parameters (mode, query, namespace).

    #[error("Namespace error: {0}")]
    Namespace(String),
    // When: Namespace validation fails (empty string, invalid characters).
    // LLM action: Provide a valid namespace string.

    #[error("Database error: {0}")]
    Database(#[from] sqlx::Error),
    // When: Underlying database error not covered by a more specific variant.
}

pub type Result<T> = std::result::Result<T, SmrtiError>;
```

---

## 9. _meta Return Format

Every dict returned by Memory includes a `_meta` key with operational metadata. The contents vary by operation type.

### search / find_similar

```json
"_meta": {
    "search_mode": "hybrid",
    "search_modes_used": ["vector", "text"],
    "namespace": ["default"],
    "total_candidates": 47,
    "duration_ms": 12.3,
    "rrf_k": 60,
    "model_name": "default"
}
```

### add_nodes

```json
"_meta": {
    "event_ids": [101, 102, 103],
    "namespace": "default",
    "count": 3,
    "duration_ms": 45.2
}
```

### get_or_create

```json
"_meta": {
    "event_id": 104,
    "namespace": "default",
    "duration_ms": 8.1
}
```

Note: `event_id` is `null` if the node already existed (no event created).

### traverse

```json
"_meta": {
    "start_node_id": "abc-123",
    "depth": 2,
    "nodes_found": 5,
    "edges_found": 4,
    "duration_ms": 6.7
}
```

### aggregate

```json
"_meta": {
    "edge_type": "SPENT",
    "namespace": ["user:123"],
    "duration_ms": 3.1
}
```

---

## 10. Hybrid Search

### 10.1 Three Modes

**vector** -- Pure cosine similarity via pgvector.

```sql
SELECT n.*, 1 - (ne.embedding <=> $1::vector) AS similarity
FROM nodes n
JOIN node_embeddings ne ON ne.node_id = n.id
WHERE n.namespace = ANY($2)
  AND n.is_retracted = FALSE
  AND ne.model_name = $3
  AND 1 - (ne.embedding <=> $1::vector) >= $4
ORDER BY ne.embedding <=> $1::vector
LIMIT $5
```

**text** -- tsvector full-text search with trigram fallback.

```sql
-- Primary: tsvector ranking
SELECT n.*, ts_rank_cd(n.search_vector, query) AS similarity
FROM nodes n, plainto_tsquery($1) query
WHERE n.namespace = ANY($2)
  AND n.is_retracted = FALSE
  AND n.search_vector @@ query
ORDER BY ts_rank_cd(n.search_vector, query) DESC
LIMIT $3

-- If tsvector returns < limit results, fallback to trigram:
SELECT n.*, similarity(n.content, $1) AS similarity
FROM nodes n
WHERE n.namespace = ANY($2)
  AND n.is_retracted = FALSE
  AND n.content % $1
  AND n.id NOT IN (... already found ...)
ORDER BY similarity(n.content, $1) DESC
LIMIT $3
```

**hybrid** -- Reciprocal Rank Fusion (RRF) of vector and text results.

```sql
WITH vector_results AS (
    SELECT n.id, n.*,
           1 - (ne.embedding <=> $1::vector) AS vector_sim,
           ROW_NUMBER() OVER (ORDER BY ne.embedding <=> $1::vector) AS vector_rank
    FROM nodes n
    JOIN node_embeddings ne ON ne.node_id = n.id
    WHERE n.namespace = ANY($2)
      AND n.is_retracted = FALSE
      AND ne.model_name = $3
    ORDER BY ne.embedding <=> $1::vector
    LIMIT $4  -- hybrid_candidate_pool
),
text_results AS (
    SELECT n.id,
           ts_rank_cd(n.search_vector, query) AS text_sim,
           ROW_NUMBER() OVER (ORDER BY ts_rank_cd(n.search_vector, query) DESC) AS text_rank
    FROM nodes n, plainto_tsquery($5, $6) query
    WHERE n.namespace = ANY($2)
      AND n.is_retracted = FALSE
      AND n.search_vector @@ query
    LIMIT $4  -- hybrid_candidate_pool
),
rrf AS (
    SELECT
        COALESCE(v.id, t.id) AS node_id,
        COALESCE(1.0 / ($7 + v.vector_rank), 0) +
        COALESCE(1.0 / ($7 + t.text_rank), 0) AS rrf_score,
        COALESCE(v.vector_sim, 0) AS similarity
    FROM vector_results v
    FULL OUTER JOIN text_results t ON v.id = t.id
)
SELECT n.*, rrf.rrf_score, rrf.similarity
FROM rrf
JOIN nodes n ON n.id = rrf.node_id
ORDER BY rrf.rrf_score DESC
LIMIT $8
```

Where `$7` is `rrf_k` (default 60) and `$4` is `hybrid_candidate_pool` (default 100).

### 10.2 Edge-Based Search Filters

The Memory class exposes flat parameters `edge_type` and `edge_target`. These are translated to an `EdgeFilter` list before calling the provider.

```rust
// Memory::search() translation:
if let Some(et) = edge_type {
    let edge_filters = vec![EdgeFilter {
        edge_type: et.to_string(),
        target_node_id: edge_target.map(|t| Uuid::parse_str(t)).transpose()?,
        ..Default::default()
    }];
}
```

The provider appends EXISTS subqueries for each EdgeFilter to the WHERE clause of the search query. See section 6.1 for the SQL pattern.

---

## 11. Design Principles

### 11.1 Append-Only Edge Semantics (A1 Prevention)

There is deliberately **no** UNIQUE constraint on `(source_node_id, target_node_id, edge_type)` in the edges table. Multiple edges of the same type between the same nodes are valid and expected.

**Why:** A unique constraint causes silent data loss. If "Alice WORKS_AT Acme" is extracted twice (once with metadata `{role: "engineer"}`, once with `{role: "manager"}`), a unique constraint would either fail or overwrite the first edge. Both outcomes are wrong. The correct model is two separate edges, potentially with different temporal validity.

This was designated "A1" (the highest-severity class of bug) during the Unspool audit.

### 11.2 Event Sourcing

The `events` table is the source of truth. The `nodes`, `edges`, and `node_embeddings` tables are projections -- materialized views that can be dropped and rebuilt from events.

**Guarantee:** `apply_event()` appends to the event log and updates projections in a single database transaction. If the projection update fails, the event is also rolled back (no ghost events).

**Rebuild:** `memory.rebuild()` drops projection tables, re-runs migrations, and replays all events from the log in order.

### 11.3 Concurrency Safety

`get_or_create_node()` uses PostgreSQL `ON CONFLICT` for atomicity:

```sql
INSERT INTO nodes (id, namespace, node_key, node_type, content, content_type, metadata)
VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
ON CONFLICT (namespace, node_key) WHERE node_key IS NOT NULL
DO NOTHING
RETURNING *;
```

If `RETURNING` yields no rows, the node already existed -- fetch it with a SELECT. No race conditions, no application-level locking.

### 11.4 No Hidden Behavior

- Every operation is explicit. No background syncs, no automatic merges, no implicit retries.
- `_meta` on every return shows exactly what happened (event IDs, modes used, duration, candidates considered).
- All operations are synchronous (await-based). No background processing.

### 11.5 Full Configurability

Every threshold, limit, algorithm choice, and default value lives in `SmrtiConfig`. No magic numbers buried in code. Every config field is documented with its type, default, validation rule, and description.

### 11.6 GDPR / Right to be Forgotten

The append-only event log is sacred for integrity — but "right to be forgotten" is law. smrti provides one intentionally destructive operation:

```rust
/// Physically delete ALL data for a namespace — events, nodes, edges, embeddings.
///
/// This is the ONLY operation that violates append-only. It is irreversible.
/// Designed for GDPR Article 17 compliance.
pub async fn purge_namespace(&self, namespace: &str) -> Result<Value>;
```

This deletes from events, nodes, edges, and node_embeddings where namespace matches. It is logged to a separate `smrti_audit_log` table (which does NOT contain user data, only the fact that a purge occurred, the namespace, and the timestamp).

Users who need more granular deletion (e.g., delete a single node's history from the event log) can extend this pattern.

### 11.7 Safe Multi-Tenant Rebuild

`rebuild()` without a namespace would drop ALL projections across ALL tenants — dangerous in production. Rules:

- `rebuild(namespace="user:123")` — replays only events for that namespace. Safe.
- `rebuild()` with no namespace — requires explicit `rebuild(all_namespaces=True)` flag. Without it, raises `ValidationError("rebuild requires namespace or all_namespaces=True")`.

### 11.8 Crash Recovery

The event log is the recovery mechanism for corrupted projections. Since projections (nodes, edges, node_embeddings) are derived from events, `rebuild()` can reconstruct them at any time. See section 15.3.

### 11.9 Scoped Namespace Context

Passing namespace to every call is error-prone. Memory provides a scoped context:

```rust
// Instead of:
memory.add_nodes(&nodes, Some("user:123")).await?;
memory.search("query", Some("user:123"), None, None, None, None, None, None, None, None, None).await?;

// Use:
let user_memory = memory.scoped("user:123");
user_memory.add_nodes(&nodes, None).await?;  // namespace="user:123" implicit
user_memory.search("query", None, None, None, None, None, None, None, None, None, None).await?;
```

In Python (via PyO3):

```python
# Instead of:
await memory.add_nodes([...], namespace="user:123")
await memory.search("query", namespace="user:123")

# Use:
user_memory = memory.scoped("user:123")
await user_memory.add_nodes([...])       # namespace="user:123" implicit
await user_memory.search("query")        # namespace="user:123" implicit
```

`scoped()` returns a lightweight wrapper that binds namespace to all calls. The underlying provider and connection pool are shared. Explicit namespace params still override the scoped default.

### 11.10 Per-Model Distance Metric

`distance_metric` in SmrtiConfig is the default, but different embedding models may require different distance functions. The distance metric can be overridden per `model_name` by storing a `distance_metric:{model_name}` key in `smrti_meta`. Callers can specify this when calling `add_nodes()` with a given `model_name`.

When creating the HNSW index, the provider checks `smrti_meta` for a model-specific distance metric first, falls back to `config.distance_metric`. The metric is stored in `smrti_meta` alongside the index info.

---

## 12. Telemetry

Telemetry uses the `tracing` crate, Rust's standard for structured diagnostics. The `tracing` crate is zero-cost when no subscriber is configured (all instrumentation compiles to no-ops). OTEL export is available via an optional `telemetry` feature flag using `tracing-opentelemetry`.

### 12.1 Implementation

```rust
// smrti-core/src/telemetry.rs
// All public methods use #[tracing::instrument] for automatic span creation.
// No runtime cost when no tracing subscriber is registered.

// Cargo.toml feature flag:
// [features]
// default = []
// telemetry = ["tracing-opentelemetry", "opentelemetry", "opentelemetry-otlp"]
```

Every public method on `PostgresProvider` is annotated with `#[tracing::instrument]`, which automatically creates spans with the method's arguments as span fields.

### 12.2 Spans

Every public method on PostgresProvider gets a span:

| Span Name | Attributes |
|-----------|-----------|
| `smrti.provider.apply_event` | `event.type`, `event.namespace` |
| `smrti.provider.get_node` | `node.id` |
| `smrti.provider.search_nodes` | `search.mode`, `search.namespaces`, `search.limit`, `search.node_type` |
| `smrti.provider.traverse_graph` | `traverse.start_node_id`, `traverse.depth`, `traverse.max_nodes` |
| `smrti.provider.aggregate_edges` | `aggregate.edge_type`, `aggregate.namespaces` |
| `smrti.provider.get_events` | `events.after_id`, `events.limit` |
| `smrti.provider.get_or_create_node` | `node.namespace`, `node.node_key`, `node.created` |
| `smrti.provider.migrate` | `migration.files_applied` |

### 12.3 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `smrti.events.total` | Counter | Total events applied, by type |
| `smrti.search.duration_ms` | Histogram | Search latency by mode |
| `smrti.search.results` | Histogram | Result count per search |
| `smrti.pool.connections` | Gauge | Active connection count |

### 12.4 _meta Correlation

The same data that populates tracing span attributes also populates the `_meta` key in Memory return values. This ensures consistency between observability and API responses.

---

## 13. Embedding & LLM Integration (Caller's Responsibility)

smrti is a **dumb storage layer** — it does not call LLMs or generate embeddings. It accepts pre-computed vectors and structured data. The intelligence lives in the caller (Konflux workflows, custom application code, or any orchestration layer).

### 13.1 How Embeddings Enter smrti

Embeddings are passed alongside nodes via `add_nodes()`:

```rust
// Caller computes embeddings externally (Ollama, OpenAI, local model, etc.)
let vectors: Vec<Vec<f32>> = my_embedding_service.embed(&texts).await?;

// smrti stores them
memory.add_nodes(&[
    NodeInput {
        node_type: "person",
        content: "Alice is an engineer",
        embedding: Some(vectors[0].clone()),
        model_name: Some("nomic-embed-text"),
        ..Default::default()
    }
]).await?;
```

If `embedding` is `None`, the node is stored without a vector. It will be searchable by text/metadata but not by vector similarity.

### 13.2 How Search Queries Work

For vector search, the caller provides the query vector:

```rust
// Caller embeds the query
let query_vec = my_embedding_service.embed(&["engineer"]).await?[0].clone();

// smrti searches
let results = memory.search(SearchOpts {
    query_vector: Some(query_vec),
    text_query: Some("engineer"),
    mode: SearchMode::Hybrid,
    ..Default::default()
}).await?;
```

For text-only search, no vector is needed:

```rust
let results = memory.search(SearchOpts {
    text_query: Some("Alice"),
    mode: SearchMode::Text,
    ..Default::default()
}).await?;
```

### 13.3 How Extraction Works (External)

smrti provides the data models (`CandidateNode`, `CandidateEdge`, `ExtractionResult`) and JSON Schema generation (via `schemars`) so callers can use them with any LLM:

```rust
// Get the JSON schema to pass to your LLM
let schema = schemars::schema_for!(ExtractionResult);

// Call your LLM externally
let llm_response = my_llm.generate(prompt, Some(schema)).await?;

// Parse the response
let extracted: ExtractionResult = serde_json::from_value(llm_response)?;

// Store via smrti
for node in extracted.nodes {
    memory.add_nodes(&[node.into()]).await?;
}
```

### 13.4 Why No Built-in LLM/Embedding

- **Unopinionated**: Users choose their own models, providers, and orchestration
- **No HTTP dependency**: smrti-core has no reqwest/HTTP client dependency
- **Konflux integration**: Konflux already has `ai:complete` and `ai:embed` tools — smrti shouldn't duplicate this
- **Leaner binary**: No LLM SDK dependencies in the core crate
- **Testable**: Tests don't need mock HTTP servers, just pre-computed vectors

---

## 15. Import/Export

### 15.1 export_events()

Returns events as a list of plain dicts. This is the complete, lossless representation of all data in smrti. Events are ordered by ID ascending.

```rust
let result = memory.export_events(Some(0), Some("user:123"), None).await?;
// result["events"] is an array of event objects
// Each: {"id": int, "namespace": str, "event_type": str,
//         "payload": object, "metadata": object|null, "created_at": str}
```

In Python (via PyO3):

```python
result = await memory.export_events(after_id=0, namespace="user:123")
# result["events"] is a list of event dicts
```

### 15.2 import_events()

Replays events through `apply_event()` in order. Each event gets a new database-assigned ID (original IDs are not preserved). This means import is additive -- it does not overwrite existing data.

```rust
let result = memory.import_events(&exported["events"]).await?;
// result["imported"] = number of events replayed
```

### 15.3 rebuild()

Drops projection tables (nodes, edges, node_embeddings), re-runs migrations to recreate them, then replays all events from the event log. The event log itself is never touched.

```rust
let result = memory.rebuild(None, true).await?;
// result["events_replayed"] = total events in the log
```

This is the recovery mechanism for corrupted projections. Since events are the source of truth and projections are derived, rebuild is always safe.

---

## 16. Consistency Enforcement Across API Surfaces

smrti ships three distribution targets (D32). All three must behave identically. This section defines how consistency is enforced.

### 16.1 Three Surfaces

| Surface | Crate | Consumer | Entry Point |
|---------|-------|----------|-------------|
| Rust | `smrti-core` | Rust applications, Konflux | `Memory` struct directly |
| Python | `smrti-python` (PyO3) | Python agent developers | `pip install smrti`, async Python class |
| Konflux | `konf-smrti` | Konflux workflow engine | In-process tool registration |

### 16.2 Rust Trait IS the Spec

The `StorageProvider` trait (section 6) is the single source of truth for provider behavior. The Rust compiler enforces that every provider implements every method with the correct signature. There is no runtime duck-typing or protocol checking — if it compiles, it conforms.

This means:
- Adding a method to `StorageProvider` forces implementation in `PostgresProvider`, `SqliteProvider`, and any future provider.
- Removing or changing a method signature is a compile-time error in all consumers.
- The trait documentation IS the behavioral contract.

### 16.3 Shared JSON Test Fixtures

Behavioral tests are defined as JSON fixtures in `tests/fixtures/`:

```
tests/fixtures/
├── add_nodes.json          # Input nodes + expected output
├── search_hybrid.json      # Query + expected results
├── traverse.json           # Start node + expected graph
├── edge_filter.json        # Filter params + expected matches
├── import_export.json      # Round-trip event data
└── ...
```

Each fixture defines:
- **Input:** method name, parameters (as JSON)
- **Expected output:** return value structure, `_meta` fields, error conditions
- **Setup:** prerequisite events to replay before the test

The same fixtures are loaded by:
1. **Rust integration tests** (`smrti-core/tests/`) — native deserialization
2. **Python integration tests** (`tests/`) — loaded via `json.load()`, called through PyO3 bindings
3. **Konflux integration tests** (`konf-smrti/tests/`) — loaded and executed as workflow tool calls

All three test suites must pass in CI. A fixture failure in any surface blocks the release.

### 16.4 Thin Python Bindings

The `smrti-python` crate contains ZERO business logic. It is purely a translation layer:

- Rust `Result<Value>` -> Python `dict` (or raises `SmrtiError`)
- Rust `async fn` -> Python `async def` (via `pyo3-asyncio`)
- Rust `SmrtiConfig` -> Python `__init__` kwargs
- Rust `SmrtiError` variants -> Python `SmrtiError` exception with `.code` attribute

No validation, no SQL, no embedding logic, no extraction logic in the Python layer. If a bug exists, it exists in `smrti-core` and is fixed once.

### 16.5 Config Validated Once

`SmrtiConfig` validation (section 5) happens in Rust. All three surfaces pass config through the same Rust validation path:

- **Rust:** `SmrtiConfig::builder().dsn("...").build()?` calls `validate()`
- **Python:** `Memory(dsn="...")` constructs `SmrtiConfig` in Rust, calls `validate()`
- **Konflux:** Tool config deserialized into `SmrtiConfig`, calls `validate()`

No surface-specific validation exists. Validation rules are defined once.

### 16.6 CI Enforcement

```
CI Pipeline:
  cargo test                    # Rust unit + integration (testcontainers)
  cargo test -p smrti-python    # PyO3 binding tests
  cargo test -p konf-smrti      # Konflux integration tests
  maturin develop && pytest     # Python-side behavioral tests (shared fixtures)
  cargo clippy -- -D warnings   # Lint
```

All must pass. Shared fixtures ensure behavioral parity across surfaces.

---

## 17. Crate Dependencies

All dependencies for `smrti-core` and related crates.

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
| `figment` | 0.10 | Config loading from environment variables, TOML files, and defaults |
| `tracing` | 0.1 | Structured diagnostics (zero-cost when no subscriber configured) |
| `tracing-opentelemetry` | 0.28 | OTEL export for tracing spans (feature-gated under `telemetry`) |
| `pyo3` | 0.22 | Python bindings (smrti-python crate only) |
| `testcontainers` | 0.23 | Integration tests with Dockerized PostgreSQL + pgvector |
| `uuid` | 1 | UUID v4 generation for node/edge/embedding IDs |
| `chrono` | 0.4 | DateTime types for timestamps and temporal validity |
| `tokio` | 1 | Async runtime |
| `async-trait` | 0.1 | Async methods in traits (StorageProvider) |

Feature flags:

| Feature | Crates Enabled | Default |
|---------|---------------|---------|
| `telemetry` | `tracing-opentelemetry`, `opentelemetry`, `opentelemetry-otlp` | off |
| `python` | `pyo3` | off (enabled only in smrti-python) |

---

*End of specification.*
